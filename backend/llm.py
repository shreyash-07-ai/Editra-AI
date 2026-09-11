import json
from .config import OPENAI_API_KEY, OPENAI_MODEL

class LLM:
    def __init__(self):
        self.client = None
        if OPENAI_API_KEY:
            from openai import OpenAI
            self.client = OpenAI(api_key=OPENAI_API_KEY)

    def text(self, system, user):
        if not self.client:
            return ""
        r = self.client.responses.create(
            model=OPENAI_MODEL,
            instructions=system,
            input=user
        )
        return r.output_text

    def json(self, system, user, fallback):
        raw = self.text(system, user)
        if not raw:
            return fallback
        try:
            return json.loads(raw)
        except Exception:
            start, end = raw.find("{"), raw.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(raw[start:end+1])
                except Exception:
                    pass
        return fallback
