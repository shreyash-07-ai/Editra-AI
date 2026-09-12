import json
import time
from google import genai
from .config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODEL


class LLM:
    """Gemini wrapper with a lightweight fallback for quota exhaustion."""

    def __init__(self):
        self.client = None
        if GEMINI_API_KEY:
            self.client = genai.Client(api_key=GEMINI_API_KEY)

    @staticmethod
    def _is_quota_error(exc):
        text = str(exc).lower()
        return "429" in text or "resource_exhausted" in text or "quota" in text

    def text(self, system, user):
        if not self.client:
            return ""

        contents = (
            f"SYSTEM INSTRUCTIONS:\n{system}\n\n"
            f"USER REQUEST:\n{user}"
        )

        models = [GEMINI_MODEL]
        if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL:
            models.append(GEMINI_FALLBACK_MODEL)

        last_error = None
        for model in models:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                )
                return response.text or ""
            except Exception as exc:
                last_error = exc
                if not self._is_quota_error(exc):
                    break
                # Do not sleep for the provider's 40+ second retry hint.
                # Try the configured lightweight fallback immediately.
                continue

        if last_error and self._is_quota_error(last_error):
            raise RuntimeError(
                "Gemini quota exhausted for the configured models. "
                "Wait for the quota reset or use a Gemini API project with billing enabled. "
                f"Primary model: {GEMINI_MODEL}; fallback: {GEMINI_FALLBACK_MODEL}. "
                f"Details: {last_error}"
            ) from last_error

        raise RuntimeError(
            "Gemini API request failed. Check GEMINI_API_KEY and GEMINI_MODEL in your .env file. "
            f"Details: {last_error}"
        ) from last_error

    def json(self, system, user, fallback):
        raw = self.text(system, user)
        if not raw:
            return fallback

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
