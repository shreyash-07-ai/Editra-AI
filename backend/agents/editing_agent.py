from ..llm import LLM


class EditingAgent:
    """Turn a natural-language follow-up into a minimal, targeted edit plan."""

    def __init__(self):
        self.llm = LLM()

    def operation_plan(self, prompt, artifact_type, structure):
        fallback = {"operations": [{"type": "noop"}]}
        system = f"""You are Editra AI's precision editing agent.
The user already has a generated {artifact_type.upper()} artifact.
Create a MINIMAL edit plan for ONLY what the user requested.
Never rewrite, summarize, reorder, or regenerate unrelated content.
Preserve all existing wording, sections, tables, slide layouts, styles and visuals
unless the requested change explicitly affects them.
Use exact paragraph/slide indexes from the supplied structure whenever possible.
Return JSON only in this shape: {{"operations":[...]}}.

DOCX operations:
replace_paragraph {{"type":"replace_paragraph","index":number,"text":"new text"}}
insert_after_heading {{"type":"insert_after_heading","heading":"exact heading","paragraphs":["..."]}}
append_section {{"type":"append_section","heading":"...","paragraphs":["..."]}}
delete_paragraph {{"type":"delete_paragraph","index":number}}
replace_table {{"type":"replace_table","table_index":number,"rows":[["...","..."]]}}

PPTX operations:
replace_shape_text {{"type":"replace_shape_text","slide":number,"old_text":"exact text","new_text":"..."}}
replace_slide_text {{"type":"replace_slide_text","slide":number,"text":"..."}}
add_slide {{"type":"add_slide","after_slide":number,"title":"...","bullets":["..."]}}
delete_slide {{"type":"delete_slide","slide":number}}
add_visual {{"type":"add_visual","slide":number,"visual":{{...}}}}

For 'update the introduction section', modify only the paragraph(s) inside that
section. Do not touch the title or any other section. If the request cannot be
performed safely, return noop instead of rewriting the artifact.
"""
        result = self.llm.json(
            system,
            f"USER REQUEST:\n{prompt}\n\nCURRENT ARTIFACT STRUCTURE:\n{structure}",
            fallback,
        )
        if not isinstance(result, dict) or not isinstance(result.get("operations"), list):
            return fallback
        return result

    def operation_plan_legacy(self, prompt):
        p = prompt.lower()
        ops = []
        if "executive summary" in p:
            ops.append("add_executive_summary")
        if "slide" in p and ("add" in p or "create" in p):
            ops.append("add_slide")
        if "concise" in p or "shorter" in p:
            ops.append("rewrite_concise")
        if "tone" in p or "professional" in p:
            ops.append("change_tone")
        if not ops:
            ops.append("general_modify")
        return ops
