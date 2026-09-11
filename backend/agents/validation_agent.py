from pathlib import Path
from docx import Document
from pptx import Presentation

class ValidationAgent:
    def validate(self, path, artifact_type):
        p = Path(path)
        if not p.exists() or p.stat().st_size == 0:
            return False, ["File missing or empty."]
        try:
            if artifact_type == "docx":
                Document(str(p))
            elif artifact_type == "pptx":
                Presentation(str(p))
            else:
                return False, ["Unsupported artifact type."]
            return True, ["Artifact opens successfully."]
        except Exception as e:
            return False, [f"Artifact validation failed: {e}"]
