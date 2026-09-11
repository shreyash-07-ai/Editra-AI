import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
PREVIEW_DIR = DATA_DIR / "previews"

for p in (UPLOAD_DIR, OUTPUT_DIR, PREVIEW_DIR):
    p.mkdir(parents=True, exist_ok=True)

# Gemini is the primary LLM provider for Editra AI.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Optional real-time web research.
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Optional enterprise RAG.
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "editra")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
