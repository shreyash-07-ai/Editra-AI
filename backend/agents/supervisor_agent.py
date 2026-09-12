from ..llm import LLM


class SupervisorAgent:
    def __init__(self):
        self.llm = LLM()

    def route(self, prompt, current_artifact, analyses):
        p = prompt.lower()
        wants_ppt = any(x in p for x in ["pptx", "ppt ", "powerpoint", "presentation", "slides", "slide deck"])
        wants_doc = any(x in p for x in ["docx", "word document", "document", "report", "proposal"])
        wants_xlsx = any(x in p for x in ["xlsx", "excel", "spreadsheet"])
        fallback = {
            "intent": "edit" if current_artifact else "create",
            "output_type": current_artifact.get("artifact_type") if current_artifact else (
                "pptx" if wants_ppt or any(x.get("type") == "pptx" for x in analyses)
                else "xlsx" if wants_xlsx
                else "docx"
            ),
            "research": any(w in p for w in ["latest", "current", "research", "web", "trends", "news"]),
            "rag": any(w in p for w in ["company", "internal", "knowledge base", "policy"]),
            "operation": "modify" if current_artifact else "generate",
            "target": "current artifact" if current_artifact else "uploaded source",
            "instructions": prompt,
        }
        system = """You are Editra AI's supervisor. Return JSON only with:
intent (create/edit), output_type (docx/pptx), research (boolean), rag (boolean),
operation (generate/modify/convert), target (string), instructions (string).
For explicit PPTX, PowerPoint, presentation or slide-deck requests choose pptx.
For explicit DOCX or Word requests choose docx.
When editing, keep the current artifact type. Preserve the existing artifact and
make only the requested change."""
        data = self.llm.json(system, prompt, fallback)
        if not isinstance(data, dict):
            data = fallback
        if current_artifact:
            data["output_type"] = current_artifact.get("artifact_type", "docx")
            data["intent"] = "edit"
            data["operation"] = "modify"
        elif wants_ppt:
            data["output_type"] = "pptx"
        elif wants_xlsx:
            data["output_type"] = "xlsx"
        elif wants_doc:
            data["output_type"] = "docx"
        data["instructions"] = data.get("instructions") or prompt
        return data
