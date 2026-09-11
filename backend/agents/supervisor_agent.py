from ..llm import LLM

class SupervisorAgent:
    def __init__(self):
        self.llm = LLM()

    def route(self, prompt, current_artifact, analyses):
        fallback = {
            "intent": "edit" if current_artifact else "create",
            "output_type": (
                current_artifact.get("artifact_type") if current_artifact
                else ("pptx" if any(x.get("type")=="pptx" for x in analyses) else "docx")
            ),
            "research": any(w in prompt.lower() for w in ["latest","current","research","web","trends","news"]),
            "rag": any(w in prompt.lower() for w in ["company","internal","knowledge base","policy"]),
            "operation": "modify" if current_artifact else "generate"
        }
        system = """You are Editra AI's supervisor. Return JSON only with:
intent (create/edit), output_type (docx/pptx), research (boolean), rag (boolean),
operation (generate/modify/convert), target (string), instructions (string).
Preserve the existing artifact when editing."""
        data = self.llm.json(system, prompt, fallback)
        data["instructions"] = data.get("instructions") or prompt
        return data
