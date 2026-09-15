import json
import threading
from google import genai
from .config import GEMINI_API_KEYS, GEMINI_MODEL, GEMINI_FALLBACK_MODEL


class LLM:
    """Gemini wrapper with five-key rotation and model fallback."""

    def __init__(self):
        self.clients = [
            genai.Client(api_key=key)
            for key in GEMINI_API_KEYS
        ]
        self._cursor = 0
        self._lock = threading.Lock()

    @staticmethod
    def _is_retryable_error(exc):
        text = str(exc).lower()
        markers = (
            "429",
            "resource_exhausted",
            "quota",
            "rate limit",
            "rate_limit",
            "too many requests",
            "503",
            "service unavailable",
            "temporarily unavailable",
            "overloaded",
        )
        return any(marker in text for marker in markers)

    def _ordered_clients(self):
        if not self.clients:
            return []

        with self._lock:
            start = self._cursor % len(self.clients)

        return [
            self.clients[(start + offset) % len(self.clients)]
            for offset in range(len(self.clients))
        ]

    def _mark_success(self, client):
        with self._lock:
            try:
                index = self.clients.index(client)
                self._cursor = (index + 1) % len(self.clients)
            except ValueError:
                pass

    def text(self, system, user):
        if not self.clients:
            return ""

        contents = (
            f"SYSTEM INSTRUCTIONS:\n{system}\n\n"
            f"USER REQUEST:\n{user}"
        )

        models = [GEMINI_MODEL]
        if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL:
            models.append(GEMINI_FALLBACK_MODEL)

        last_error = None

        # Start from the next key after the previous successful request.
        # If a key is rate-limited/quota-exhausted, immediately try the next
        # project instead of waiting for the provider retry window.
        for client in self._ordered_clients():
            for model in models:
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=contents,
                    )
                    self._mark_success(client)
                    return response.text or ""
                except Exception as exc:
                    last_error = exc
                    # Continue to the fallback model for this key, then move
                    # to the next API key if the request still fails.
                    continue

        if last_error:
            if self._is_retryable_error(last_error):
                raise RuntimeError(
                    f"All {len(self.clients)} configured Gemini API keys are "
                    "currently quota/rate limited or unavailable. "
                    f"Models tried: {', '.join(models)}. Details: {last_error}"
                ) from last_error

            raise RuntimeError(
                "Gemini API request failed across all configured API keys. "
                "Check GEMINI_API_KEY_1 through GEMINI_API_KEY_5 and the "
                f"configured models. Details: {last_error}"
            ) from last_error

        return ""

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
