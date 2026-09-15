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

# Gemini models. Five API keys are supported so requests can fail over to the
# next configured project when one key reaches a quota/rate limit.
GEMINI_API_KEYS = [
    os.getenv(f"GEMINI_API_KEY_{i}", "").strip()
    for i in range(1, 6)
]
GEMINI_API_KEYS = list(dict.fromkeys(key for key in GEMINI_API_KEYS if key))

# Backward compatibility: an older single-key .env still works as API #1.
legacy_gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
if legacy_gemini_key and legacy_gemini_key not in GEMINI_API_KEYS:
    GEMINI_API_KEYS.insert(0, legacy_gemini_key)

# Existing imports can continue using this value as the primary key.
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "editra")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "default")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))
