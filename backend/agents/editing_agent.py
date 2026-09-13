from ..llm import LLM


class EditingAgent:
    """Translate natural-language requests into minimal edits on the current artifact."""

    def __init__(self):
        self.llm = LLM()

    def operation_plan(self, prompt, artifact_type, structure):
        p = (prompt or "").lower().strip()

        if artifact_type == "docx":
            visual = any(x in p for x in ["graph", "chart", "plot", "visual", "diagram"])
            implementation = any(x in p for x in ["implementation plan", "implementation table", "implementation"])
            describe = any(x in p for x in ["describe the document", "describe document", "document description", "summarize the document", "summary of the document"])

            if describe:
                return {"operations": [{"type": "insert_description_at_beginning"}]}

            if "executive summary" in p and any(x in p for x in ["add", "create", "insert"]):
                return {"operations": [{"type": "insert_executive_summary_at_beginning"}]}

            if "implementation plan" in p and any(x in p for x in ["more detailed", "detail", "expand", "enhance"]):
                return {"operations": [{"type": "detail_implementation_table", "table_index": 0}]}

            if "success metrics" in p and any(x in p for x in ["shorten", "shorter", "concise", "brief"]):
                return {"operations": [{"type": "shorten_section_paragraph", "heading": "6. Success Metrics"}]}

            if implementation and visual:
                if "replace" in p and "table" in p and any(x in p for x in ["with table", "with the table", "back to table", "to table"]):
                    return {"operations": [{"type": "replace_visual_with_table", "table_index": 0}]}
                if ("replace" in p and "table" in p) or "table to graph" in p or "table into graph" in p or "change the implementation plan table to graph" in p:
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

        fallback = {"operations": [{"type": "noop"}]}

        if artifact_type == "xlsx":
            system = """You are Editra AI's precision spreadsheet editing agent.
The user already has an existing XLSX artifact.
Create a MINIMAL edit plan for ONLY what the user requested.
Never rewrite or regenerate unrelated sheets, rows or columns.
Use exact sheet names from the supplied structure whenever possible.
Return JSON only in this shape: {"operations":[...]}.

Operations:
set_cell {"type":"set_cell","sheet":"Sheet1","cell":"B2","value":"..."}
add_row {"type":"add_row","sheet":"Sheet1","values":["...","..."]}
delete_row {"type":"delete_row","sheet":"Sheet1","row":number}
add_column {"type":"add_column","sheet":"Sheet1","header":"...","values":["..."]}
add_sheet {"type":"add_sheet","name":"...","headers":["..."],"rows":[["..."]]}
rename_sheet {"type":"rename_sheet","old_name":"...","new_name":"..."}
delete_sheet {"type":"delete_sheet","name":"..."}
replace_range {"type":"replace_range","sheet":"Sheet1","start_cell":"A1","rows":[["..."]]}

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

        system = f"""You are Editra AI's precision editing agent.
The user already has an existing {artifact_type.upper()} artifact.
Create a MINIMAL edit plan for ONLY what the user requested.
The output must be an edited copy of the current artifact, never a newly recreated document.
Never rewrite, summarize, reorder, or regenerate unrelated content.
Preserve all existing wording, sections, tables, slide layouts, styles and visuals
unless the requested change explicitly affects them.
Use exact paragraph/slide indexes from the supplied structure whenever possible.
Return JSON only in this shape: {{"operations":[...]}}.

DOCX operations:
replace_paragraph {{"type":"replace_paragraph","index":number,"text":"new text"}}
insert_after_heading {{"type":"insert_after_heading","heading":"exact heading","paragraphs":["..."]}}
insert_section_after_heading {{"type":"insert_section_after_heading","after_heading":"exact heading","heading":"...","paragraphs":["..."]}}
insert_description_at_beginning {{"type":"insert_description_at_beginning"}}
insert_executive_summary_at_beginning {{"type":"insert_executive_summary_at_beginning"}}
shorten_section_paragraph {{"type":"shorten_section_paragraph","heading":"exact heading"}}
detail_implementation_table {{"type":"detail_implementation_table","table_index":number}}
append_section {{"type":"append_section","heading":"...","paragraphs":["..."]}}
delete_paragraph {{"type":"delete_paragraph","index":number}}
replace_table {{"type":"replace_table","table_index":number,"rows":[["...","..."]]}}
add_chart_from_tables {{"type":"add_chart_from_tables","table_index":number,"chart_kind":"bar|pie","title":"..."}}
replace_table_with_chart {{"type":"replace_table_with_chart","table_index":number,"chart_kind":"bar|pie","title":"..."}}
replace_visual_with_table {{"type":"replace_visual_with_table","table_index":number}}
remove_visuals {{"type":"remove_visuals"}}

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
