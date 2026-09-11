from ..llm import LLM


class EditingAgent:
    """Create safe, minimal operations for conversational artifact editing."""

    def __init__(self):
        self.llm = LLM()

    def operation_plan(self, prompt, artifact_type, structure):
        p = (prompt or "").lower().strip()

        if artifact_type == "docx":
            visual = any(x in p for x in ["graph", "chart", "plot", "visual", "diagram"])
            implementation = any(x in p for x in ["implementation plan", "implementation table", "implementation"])

            if visual and implementation:
                if ("replace" in p and "table" in p and visual) or "table to graph" in p or "table into graph" in p:
                    return {"operations": [{
                        "type": "replace_table_with_chart",
                        "table_index": 0,
                        "chart_kind": "bar",
                        "title": "Implementation Plan — Duration by Activity",
                    }]}
                return {"operations": [{
                    "type": "add_chart_from_tables",
                    "table_index": 0,
                    "chart_kind": "bar",
                    "title": "Implementation Plan — Duration by Activity",
                }]}

            if ("remove" in p or "delete" in p) and visual:
                return {"operations": [{"type": "remove_visuals"}]}

            if "replace" in p and "graph" in p and "table" in p:
                return {"operations": [{"type": "replace_visual_with_table", "table_index": 0}]}

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
add_chart_from_tables {{"type":"add_chart_from_tables","table_index":number,"chart_kind":"bar|pie","title":"..."}}
replace_table_with_chart {{"type":"replace_table_with_chart","table_index":number,"chart_kind":"bar|pie","title":"..."}}
remove_visuals {{"type":"remove_visuals"}}
replace_visual_with_table {{"type":"replace_visual_with_table","table_index":number}}

PPTX operations:
replace_shape_text {{"type":"replace_shape_text","slide":number,"old_text":"exact text","new_text":"..."}}
replace_slide_text {{"type":"replace_slide_text","slide":number,"text":"..."}}
add_slide {{"type":"add_slide","after_slide":number,"title":"...","bullets":["..."]}}
delete_slide {{"type":"delete_slide","slide":number}}
add_visual {{"type":"add_visual","slide":number,"visual":{{...}}}}

If the request cannot be performed safely, return noop instead of rewriting the artifact.
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
