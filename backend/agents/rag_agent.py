from ..config import GEMINI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX, PINECONE_NAMESPACE, EMBEDDING_MODEL, EMBEDDING_DIMENSION


class RAGAgent:
    def __init__(self):
        self.enabled = bool(PINECONE_API_KEY and GEMINI_API_KEY)

    def _embed(self, text):
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=EMBEDDING_DIMENSION,
            ),
        )
        return result.embeddings[0].values

    def retrieve(self, query, top_k=5):
        if not self.enabled:
            return []
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(PINECONE_INDEX)
        result = index.query(
            vector=self._embed(query),
            top_k=top_k,
            include_metadata=True,
            namespace=PINECONE_NAMESPACE,
        )
        matches = getattr(result, "matches", None)
        if matches is None and isinstance(result, dict):
            matches = result.get("matches", [])
        output = []
        for match in matches or []:
            metadata = getattr(match, "metadata", None)
            if metadata is None and isinstance(match, dict):
                metadata = match.get("metadata", {})
            output.append(metadata or {})
        return output
