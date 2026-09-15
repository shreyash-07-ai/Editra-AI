from ..config import (
    GEMINI_API_KEYS,
    PINECONE_API_KEY,
    PINECONE_INDEX,
    PINECONE_NAMESPACE,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
)


class RAGAgent:
    """Document-first RAG with Pinecone and resilient five-key Gemini fallback."""

    def __init__(self):
        self.enabled = bool(PINECONE_API_KEY and GEMINI_API_KEYS)
        self._local_indexes = {}
        self._gemini_clients = []
        self._gemini_cursor = 0
        self._pinecone_client = None
        self.last_remote_error = None
        self._create_clients()

    def _create_clients(self):
        if GEMINI_API_KEYS and not self._gemini_clients:
            from google import genai

            self._gemini_clients = [
                genai.Client(api_key=key)
                for key in GEMINI_API_KEYS
            ]

        if PINECONE_API_KEY and self._pinecone_client is None:
            from pinecone import Pinecone

            self._pinecone_client = Pinecone(api_key=PINECONE_API_KEY)

    def _reset_pinecone_client(self):
        if not PINECONE_API_KEY:
            return None

        from pinecone import Pinecone

        self._pinecone_client = Pinecone(api_key=PINECONE_API_KEY)
        return self._pinecone_client

    def _reset_gemini_client(self, index):
        if not GEMINI_API_KEYS or index >= len(GEMINI_API_KEYS):
            return None

        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEYS[index])
        self._gemini_clients[index] = client
        return client

    @staticmethod
    def _is_retryable_error(exc):
        text = str(exc).lower()
        markers = (
            "429",
            "resource_exhausted",
            "quota",
            "rate limit",
            "rate_limit",
            "too many requests",
            "503",
            "service unavailable",
            "temporarily unavailable",
            "overloaded",
            "client has been closed",
        )
        return any(marker in text for marker in markers)

    def _ordered_gemini_clients(self):
        if not self._gemini_clients:
            return []

        start = self._gemini_cursor % len(self._gemini_clients)
        return [
            (start + offset) % len(self._gemini_clients)
            for offset in range(len(self._gemini_clients))
        ]

    def _mark_gemini_success(self, index):
        if self._gemini_clients:
            self._gemini_cursor = (index + 1) % len(self._gemini_clients)

    def _embed(self, text, task_type):
        if not self._gemini_clients:
            return None

        from google.genai import types

        last_error = None

        for index in self._ordered_gemini_clients():
            client = self._gemini_clients[index]

            try:
                result = client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=text,
                    config=types.EmbedContentConfig(
                        task_type=task_type,
                        output_dimensionality=EMBEDDING_DIMENSION,
                    ),
                )
                self._mark_gemini_success(index)
                return result.embeddings[0].values

            except Exception as exc:
                last_error = exc

                # Recreate a closed client and retry once with the same key.
                if "client has been closed" in str(exc).lower():
                    try:
                        client = self._reset_gemini_client(index)
                        result = client.models.embed_content(
                            model=EMBEDDING_MODEL,
                            contents=text,
                            config=types.EmbedContentConfig(
                                task_type=task_type,
                                output_dimensionality=EMBEDDING_DIMENSION,
                            ),
                        )
                        self._mark_gemini_success(index)
                        return result.embeddings[0].values
                    except Exception as retry_exc:
                        last_error = retry_exc

                # Quota/rate-limit errors move immediately to the next key.
                # Other errors also move on so one bad project cannot block RAG.
                continue

        if last_error:
            raise RuntimeError(
                f"All {len(self._gemini_clients)} configured Gemini API keys "
                f"failed during embedding. Details: {last_error}"
            ) from last_error

        return None

    def embed_documents(self, texts):
        return [
            self._embed(text, "RETRIEVAL_DOCUMENT")
            for text in texts
        ]

    @staticmethod
    def _pinecone_metadata(chunk, document_id):
        """
        Convert application chunk metadata into Pinecone-safe metadata.

        Pinecone metadata values can only be:
        - string
        - number
        - boolean
        - list of strings

        Nested dictionaries are not allowed.
        """

        metadata = {
            "document_id": str(document_id),
            "content": str(chunk.get("content", "")),
            "section": str(chunk.get("section", "")),
            "page_number": int(chunk.get("page_number", 0) or 0),
            "content_type": str(
                chunk.get("content_type", "text") or "text"
            ),
            "source": str(chunk.get("source", "") or ""),
        }

        extra_metadata = chunk.get("metadata") or {}

        if isinstance(extra_metadata, dict):
            for key, value in extra_metadata.items():
                field_name = f"meta_{key}"

                if isinstance(value, (str, int, float, bool)):
                    metadata[field_name] = value

                elif isinstance(value, (list, tuple)):
                    if all(isinstance(item, str) for item in value):
                        metadata[field_name] = list(value)
                    else:
                        metadata[field_name] = str(value)

                elif value is not None:
                    metadata[field_name] = str(value)

        return metadata

    def index_document(self, document_id, chunks):
        if not chunks:
            return {
                "enabled": self.enabled,
                "chunks": 0,
                "stored": 0,
                "fallback": False,
            }

        # Always keep vectors locally so generation can continue even
        # when Pinecone is unavailable.
        if not GEMINI_API_KEYS:
            self._local_indexes[document_id] = [
                (f"{document_id}:{i}", None, chunk)
                for i, chunk in enumerate(chunks)
            ]

            return {
                "enabled": False,
                "chunks": len(chunks),
                "stored": 0,
                "fallback": True,
            }

        vectors = self.embed_documents(
            [chunk["content"] for chunk in chunks]
        )

        records = [
            (f"{document_id}:{i}", vector, chunk)
            for i, (chunk, vector) in enumerate(
                zip(chunks, vectors)
            )
        ]

        self._local_indexes[document_id] = records

        if not (self.enabled and self._pinecone_client):
            return {
                "enabled": False,
                "chunks": len(chunks),
                "stored": 0,
                "fallback": True,
            }

        payload = []

        for record_id, vector, chunk in records:
            payload.append(
                {
                    "id": record_id,
                    "values": vector,
                    "metadata": self._pinecone_metadata(
                        chunk,
                        document_id,
                    ),
                }
            )

        try:
            index = self._pinecone_client.Index(
                PINECONE_INDEX
            )

            index.upsert(
                vectors=payload,
                namespace=PINECONE_NAMESPACE,
            )

            return {
                "enabled": True,
                "chunks": len(chunks),
                "stored": len(records),
                "fallback": False,
            }

        except Exception as exc:
            self.last_remote_error = exc
            self.enabled = False

            return {
                "enabled": False,
                "chunks": len(chunks),
                "stored": 0,
                "fallback": True,
                "error": str(exc),
            }

    @staticmethod
    def _cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))

        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5

        return dot / (na * nb) if na and nb else 0.0

    @staticmethod
    def _lexical_score(query, text):
        import re

        words = {
            word
            for word in re.findall(
                r"[a-zA-Z0-9]+",
                query.lower(),
            )
            if len(word) > 2
        }

        body = text.lower()

        return sum(
            1 for word in words if word in body
        ) / max(1, len(words))

    def retrieve(
        self,
        query,
        document_id=None,
        top_k=6,
    ):
        # First try Pinecone.
        if self.enabled and self._pinecone_client:
            try:
                qvector = self._embed(
                    query,
                    "RETRIEVAL_QUERY",
                )

                kwargs = {
                    "vector": qvector,
                    "top_k": top_k,
                    "include_metadata": True,
                    "namespace": PINECONE_NAMESPACE,
                }

                if document_id:
                    kwargs["filter"] = {
                        "document_id": {
                            "$eq": str(document_id)
                        }
                    }

                index = self._pinecone_client.Index(
                    PINECONE_INDEX
                )

                result = index.query(**kwargs)

                matches = getattr(
                    result,
                    "matches",
                    None,
                )

                if matches is None and isinstance(result, dict):
                    matches = result.get(
                        "matches",
                        [],
                    )

                output = []

                for match in matches or []:
                    metadata = getattr(
                        match,
                        "metadata",
                        None,
                    )

                    score = getattr(
                        match,
                        "score",
                        None,
                    )

                    if isinstance(match, dict):
                        metadata = match.get(
                            "metadata",
                            metadata,
                        )

                        score = match.get(
                            "score",
                            score,
                        )

                    item = dict(metadata or {})
                    item["score"] = score

                    output.append(item)

                return output

            except Exception as exc:
                self.last_remote_error = exc
                self.enabled = False

        # Local semantic fallback.
        records = self._local_indexes.get(
            document_id or "",
            [],
        )

        if GEMINI_API_KEYS and self._gemini_clients:
            try:
                qvector = self._embed(
                    query,
                    "RETRIEVAL_QUERY",
                )

                ranked = sorted(
                    (
                        (
                            self._cosine(
                                qvector,
                                vector,
                            ),
                            chunk,
                        )
                        for _, vector, chunk in records
                        if vector
                    ),
                    key=lambda item: item[0],
                    reverse=True,
                )

                return [
                    dict(
                        chunk,
                        score=score,
                    )
                    for score, chunk in ranked[:top_k]
                ]

            except Exception:
                pass

        # Final lexical fallback.
        ranked = sorted(
            (
                (
                    self._lexical_score(
                        query,
                        chunk.get(
                            "content",
                            "",
                        ),
                    ),
                    chunk,
                )
                for _, _, chunk in records
            ),
            key=lambda item: item[0],
            reverse=True,
        )

        return [
            dict(
                chunk,
                score=score,
            )
            for score, chunk in ranked[:top_k]
        ]
