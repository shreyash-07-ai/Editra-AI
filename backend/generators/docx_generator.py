from copy import deepcopy
from pathlib import Path
import shutil

from docx import Document
from docx.shared import Inches
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph

from ..llm import LLM


class DOCXGenerator:
    def __init__(self):
        self.llm = LLM()

    def generate(self, output_path, prompt, source_text="", existing=None, template_path=None, edit_plan=None):
        # Editing always starts from the actual previous artifact, never from a newly
        # generated blank document. This is the key to preserving unrelated content.
        base = existing.get("path") if existing else template_path
        if base and Path(base).exists():
            shutil.copy2(base, output_path)
            if edit_plan:
                return self.apply_edit_plan(output_path, edit_plan)
            # First-generation workflow: preserve the uploaded document and append
            # only a requested AI-generated addition when the user asks for one.
            if self._needs_generated_content(prompt):
                doc = Document(output_path)
                addition = self._generate_addition(prompt, source_text)
                if addition:
                    doc.add_page_break()
                    doc.add_heading(addition.get("heading", "Editra AI Analysis"), 1)
                    for p in addition.get("paragraphs", []):
                        doc.add_paragraph(p)
                    doc.save(output_path)
            return output_path

        # No template: create a new editable artifact from the supplied content.
        content = self.llm.json(
            """Create a professional document using the supplied source material.
Return JSON only: {\"title\":\"...\",\"sections\":[{\"heading\":\"...\",\"paragraphs\":[\"...\"]}]}.
Use the source as the factual basis and cover the relevant source content. Do not invent facts.""",
            f"REQUEST:\n{prompt}\nSOURCE:\n{source_text}",
            {"title":"Editra AI Document", "sections":[{"heading":"Source Content", "paragraphs":[source_text[:5000]]}]},
        )
        doc = Document()
        doc.sections[0].top_margin = Inches(.7)
        doc.sections[0].bottom_margin = Inches(.7)
        doc.add_heading(content.get("title", "Editra AI Document"), 0)
        for section in content.get("sections", []):
            doc.add_heading(section.get("heading", "Section"), 1)
            for paragraph in section.get("paragraphs", []):
                doc.add_paragraph(paragraph)
        doc.save(output_path)
        return output_path

    def _needs_generated_content(self, prompt):
        p = prompt.lower()
        return any(x in p for x in ["create", "generate", "add", "summary", "analy", "describe", "proposal", "report"])

    def _generate_addition(self, prompt, source_text):
        return self.llm.json(
            """Generate one useful addition to an existing document. Return JSON only:
{\"heading\":\"...\",\"paragraphs\":[\"...\"]}.
Base it only on the supplied source and user request. Keep the original document unchanged.""",
            f"REQUEST:\n{prompt}\nSOURCE:\n{source_text}",
            {"heading":"Editra AI Analysis", "paragraphs":["The uploaded document was preserved as the source artifact."]},
        )

    def apply_edit_plan(self, path, plan):
        doc = Document(path)
        for op in plan.get("operations", []):
            kind = op.get("type")
            if kind == "replace_paragraph":
                self._replace_paragraph(doc, int(op.get("index", -1)), op.get("text", ""))
            elif kind == "delete_paragraph":
                self._delete_paragraph(doc, int(op.get("index", -1)))
            elif kind == "insert_after_heading":
                self._insert_after_heading(doc, op.get("heading", ""), op.get("paragraphs", []))
            elif kind == "append_section":
                doc.add_heading(op.get("heading", "Section"), 1)
                for text in op.get("paragraphs", []):
                    doc.add_paragraph(text)
            elif kind == "replace_table":
                self._replace_table(doc, int(op.get("table_index", -1)), op.get("rows", []))
        doc.save(path)
        return path

    def _replace_paragraph(self, doc, index, text):
        if 0 <= index < len(doc.paragraphs):
            p = doc.paragraphs[index]
            style = p.style
            p.clear()
            p.style = style
            p.add_run(text)

    def _delete_paragraph(self, doc, index):
        if 0 <= index < len(doc.paragraphs):
            p = doc.paragraphs[index]._element
            p.getparent().remove(p)

    def _insert_after_heading(self, doc, heading, paragraphs):
        for p in doc.paragraphs:
            if p.text.strip().lower() == heading.strip().lower():
                anchor = p._p
                for text in paragraphs:
                    new_p = OxmlElement("w:p")
                    anchor.addnext(new_p)
                    new_para = Paragraph(new_p, p._parent)
                    new_para.style = doc.styles["Normal"]
                    new_para.add_run(text)
                    anchor = new_p
                return

    def _replace_table(self, doc, table_index, rows):
        if not (0 <= table_index < len(doc.tables)):
            return
        table = doc.tables[table_index]
        while len(table.rows) < len(rows):
            table.add_row()
        for r, values in enumerate(rows):
            if r >= len(table.rows):
                break
            for c, value in enumerate(values):
                if c < len(table.rows[r].cells):
                    table.rows[r].cells[c].text = str(value)
