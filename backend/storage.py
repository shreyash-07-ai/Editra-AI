from pathlib import Path
import shutil, uuid, json
from datetime import datetime
from .config import UPLOAD_DIR, OUTPUT_DIR, PREVIEW_DIR

MIME = {
    ".docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx":"application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

class ArtifactStore:
    def __init__(self):
        self.history = {}

    def save_upload(self, filename, data):
        safe = Path(filename).name
        path = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{safe}"
        path.write_bytes(data)
        return path

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
