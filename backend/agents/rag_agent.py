from ..config import (
    GEMINI_API_KEY,
    PINECONE_API_KEY,
    PINECONE_INDEX,
    PINECONE_NAMESPACE,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
)


class RAGAgent:
    """Document-first RAG: embed source chunks, index them, then retrieve by query."""

    def __init__(self):
        self.enabled = bool(PINECONE_API_KEY and GEMINI_API_KEY)
        self._local_indexes = {}

    def _client(self):
        from google import genai
        return genai.Client(api_key=GEMINI_API_KEY)

    def _embed(self, text, task_type):
        from google.genai import types
        result = self._client().models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=EMBEDDING_DIMENSION,
            ),
        )
        return result.embeddings[0].values

    def embed_documents(self, texts):
        return [self._embed(text, "RETRIEVAL_DOCUMENT") for text in texts]

    def index_document(self, document_id, chunks):
        """Embed and upsert chunks. Returns indexing statistics for observability."""
        if not chunks:
            return {"enabled": self.enabled, "chunks": 0, "stored": 0}

        vectors = self.embed_documents([c["content"] for c in chunks])
        records = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            records.append((f"{document_id}:{i}", vector, chunk))

        self._local_indexes[document_id] = records
        stored = 0
        if self.enabled:
            from pinecone import Pinecone
            pc = Pinecone(api_key=PINECONE_API_KEY)
            index = pc.Index(PINECONE_INDEX)
            index.upsert(
                vectors=[
                    {
                        "id": rid,
                        "values": vector,
                        "metadata": {
                            "document_id": document_id,
                            "content": chunk["content"],
                            "section": chunk.get("section", ""),
                            "page_number": chunk.get("page_number", 0),
                            "content_type": chunk.get("content_type", "text"),
                            "source": chunk.get("source", ""),
                            "metadata": chunk.get("metadata", {}),
                        },
                    }
                    for rid, vector, chunk in records
                ],
                namespace=PINECONE_NAMESPACE,
            )
            stored = len(records)
        return {"enabled": self.enabled, "chunks": len(chunks), "stored": stored}

    @staticmethod
    def _cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    def retrieve(self, query, document_id=None, top_k=6):
        if not GEMINI_API_KEY:
            return []
        qvector = self._embed(query, "RETRIEVAL_QUERY")

        if self.enabled:
            from pinecone import Pinecone
            pc = Pinecone(api_key=PINECONE_API_KEY)
            index = pc.Index(PINECONE_INDEX)
            kwargs = {
                "vector": qvector,
                "top_k": top_k,
                "include_metadata": True,
                "namespace": PINECONE_NAMESPACE,
            }
            if document_id:
                kwargs["filter"] = {"document_id": {"$eq": document_id}}
            result = index.query(**kwargs)
            matches = getattr(result, "matches", None)
            if matches is None and isinstance(result, dict):
                matches = result.get("matches", [])
            output = []
            for match in matches or []:
                metadata = getattr(match, "metadata", None)
                score = getattr(match, "score", None)
                if isinstance(match, dict):
                    metadata = match.get("metadata", metadata)
                    score = match.get("score", score)
                item = dict(metadata or {})
                item["score"] = score
                output.append(item)
            return output

        # Graceful development fallback when Pinecone is not configured. The
        # same document/query embeddings are still used for semantic ranking.
        records = self._local_indexes.get(document_id or "", [])
        ranked = sorted(
            ((self._cosine(qvector, vector), chunk) for _, vector, chunk in records),
            key=lambda x: x[0],
            reverse=True,
        )
        return [dict(chunk, score=score) for score, chunk in ranked[:top_k]]
