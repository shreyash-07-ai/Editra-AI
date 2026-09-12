from pathlib import Path
import shutil, uuid, json
from datetime import datetime
from .config import UPLOAD_DIR, OUTPUT_DIR, PREVIEW_DIR

MIME = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
}

class ArtifactStore:
    def __init__(self):
        self.history = {}
        self.originals = {}

    def save_upload(self, filename, data):
        safe = Path(filename).name
        path = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{safe}"
        path.write_bytes(data)
        return path

    def set_original(self, conversation_id, path):
        """Remember the first uploaded file for a conversation so the user can
        later ask to go back to the original, even after many edited versions."""
        self.originals.setdefault(conversation_id, str(path))

    def original_path(self, conversation_id):
        return self.originals.get(conversation_id)

    def new_output(self, ext, version):
        aid = uuid.uuid4().hex[:10]
        path = OUTPUT_DIR / f"editra_{aid}_v{version}{ext}"
        return aid, path

    def preview_dir(self, aid):
        p = PREVIEW_DIR / aid
        p.mkdir(parents=True, exist_ok=True)
        return p

    def register(self, artifact):
        self.history.setdefault(artifact["conversation_id"], []).append(artifact)

    def versions(self, conversation_id):
        return self.history.get(conversation_id, [])
