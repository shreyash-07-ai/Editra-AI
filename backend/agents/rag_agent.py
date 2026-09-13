from ..config import (
    GEMINI_API_KEY,
    PINECONE_API_KEY,
    PINECONE_INDEX,
    PINECONE_NAMESPACE,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
)


class RAGAgent:
    """Document-first RAG with Pinecone and a resilient local fallback."""

    def __init__(self):
        self.enabled = bool(PINECONE_API_KEY and GEMINI_API_KEY)
        self._local_indexes = {}
        self._gemini_client = None
        self._pinecone_client = None
        self.last_remote_error = None
        self._create_clients()

    def _create_clients(self):
        if GEMINI_API_KEY and self._gemini_client is None:
            from google import genai

            self._gemini_client = genai.Client(api_key=GEMINI_API_KEY)

        if PINECONE_API_KEY and self._pinecone_client is None:
            from pinecone import Pinecone

            self._pinecone_client = Pinecone(api_key=PINECONE_API_KEY)

    def _reset_pinecone_client(self):
        if not PINECONE_API_KEY:
            return None

        from pinecone import Pinecone

        self._pinecone_client = Pinecone(api_key=PINECONE_API_KEY)
        return self._pinecone_client

    def _reset_gemini_client(self):
        if not GEMINI_API_KEY:
            return None

        from google import genai

        self._gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        return self._gemini_client

    def _embed(self, text, task_type):
        if not self._gemini_client:
            return None

        from google.genai import types

        try:
            result = self._gemini_client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=EMBEDDING_DIMENSION,
                ),
            )
        except Exception as exc:
            if "client has been closed" not in str(exc).lower():
                raise

            self._reset_gemini_client()

            result = self._gemini_client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=EMBEDDING_DIMENSION,
                ),
            )

        return result.embeddings[0].values

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
                    # Pinecone supports lists of strings.
                    if all(isinstance(item, str) for item in value):
                        metadata[field_name] = list(value)
                    else:
                        metadata[field_name] = str(value)

                elif value is not None:
                    # Convert dictionaries/other objects to strings
                    # instead of sending nested objects to Pinecone.
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
        if not GEMINI_API_KEY:
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

        # IMPORTANT:
        # Build Pinecone-safe metadata instead of passing the
        # original nested chunk["metadata"] dictionary.
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
            # Pinecone problems should never prevent local RAG
            # retrieval/generation from continuing.
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
                # Disable remote retrieval and continue with
                # local semantic retrieval.
                self.last_remote_error = exc
                self.enabled = False

        # Local semantic fallback.
        records = self._local_indexes.get(
            document_id or "",
            [],
        )

        if GEMINI_API_KEY and self._gemini_client:
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