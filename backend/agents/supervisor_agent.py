from ..llm import LLM
import re


class SupervisorAgent:
    def __init__(self):
        self.llm = LLM()

    def route(self, prompt, current_artifact, analyses):
        p = prompt.lower()
        wants_ppt = bool(re.search(r"\bppts?\b|\bpptx\b|powerpoint|presentation|\bslides?\b|slide deck", p))
        wants_xlsx = bool(re.search(r"\bxlsx\b|\bexcel\b|spreadsheet", p))
        wants_doc = bool(re.search(r"\bdocx\b|word document|\bdocument\b|\breport\b|\bproposal\b", p))
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
intent (create/edit), output_type (docx/pptx/xlsx), research (boolean), rag (boolean),
operation (generate/modify/convert), target (string), instructions (string).
For explicit PPTX, PowerPoint, presentation or slide-deck requests choose pptx.
For explicit DOCX or Word requests choose docx.
For explicit XLSX, Excel or spreadsheet requests choose xlsx.
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
