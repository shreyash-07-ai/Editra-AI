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

# Gemini models. The fallback is useful during free-tier quota exhaustion.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "editra")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "default")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))
