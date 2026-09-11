import json
from google import genai
from .config import GEMINI_API_KEY, GEMINI_MODEL


class LLM:
    """Small provider wrapper used by Editra agents.

    Gemini is the primary model provider. Keeping this wrapper means the
    Supervisor and generation agents do not need provider-specific code.
    """

    def __init__(self):
        self.client = None
        if GEMINI_API_KEY:
            self.client = genai.Client(api_key=GEMINI_API_KEY)

    def text(self, system, user):
        if not self.client:
            return ""

        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=(
                    f"SYSTEM INSTRUCTIONS:\n{system}\n\n"
                    f"USER REQUEST:\n{user}"
                ),
            )
            return response.text or ""
        except Exception as exc:
            raise RuntimeError(
                "Gemini API request failed. Check GEMINI_API_KEY and "
                f"GEMINI_MODEL in your .env file. Details: {exc}"
            ) from exc

    def json(self, system, user, fallback):
        raw = self.text(system, user)
        if not raw:
            return fallback

        # Gemini can occasionally wrap JSON in a markdown code fence.
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].lstrip()

        try:
            return json.loads(cleaned)
        except Exception:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(cleaned[start:end + 1])
                except Exception:
                    pass

        return fallback
