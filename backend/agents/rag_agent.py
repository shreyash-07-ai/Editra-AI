from ..config import PINECONE_API_KEY, PINECONE_INDEX, EMBEDDING_MODEL

class RAGAgent:
    def __init__(self):
        self.enabled = bool(PINECONE_API_KEY)

    def retrieve(self, query, top_k=5):
        if not self.enabled:
            return []
        from openai import OpenAI
        from pinecone import Pinecone
        import os
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(PINECONE_INDEX)
        emb = client.embeddings.create(model=EMBEDDING_MODEL, input=query).data[0].embedding
        result = index.query(vector=emb, top_k=top_k, include_metadata=True)
        return [
            m.get("metadata", {}) for m in result.get("matches", [])
        ]
