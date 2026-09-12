from pathlib import Path
import shutil
import re
import tempfile
import json

from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph

from ..llm import LLM


class DOCXGenerator:
    """Generate and edit DOCX files while preserving the existing artifact."""

    BACKUP_PREFIX = "EDITRA_TABLE_BACKUP::"
    CHART_CAPTION_PREFIX = "EDITRA_CHART::"

    def __init__(self):
        self.llm = LLM()

    def generate(self, output_path, prompt, source_text="", existing=None, template_path=None, edit_plan=None):
        base = existing.get("path") if existing else template_path
        if base and Path(base).exists():
            shutil.copy2(base, output_path)
            doc = Document(output_path)
            if edit_plan:
                self.apply_edit_plan(output_path, edit_plan, source_text=source_text)
                return output_path
            if self._needs_generated_content(prompt):
                addition = self._generate_addition(prompt, source_text)
                if addition:
                    self._insert_generated_section(doc, addition)
            self._polish_layout(doc)
            doc.save(output_path)
            return output_path

        content = self.llm.json(
            """Create a professional document using the supplied source material.
Return JSON only: {\"title\":\"...\",\"sections\":[{\"heading\":\"...\",\"paragraphs\":[\"...\"]}]}.
Use the source as the factual basis and cover relevant source content. Do not invent facts.""",
            f"REQUEST:\n{prompt}\nSOURCE:\n{source_text}",
            {"title":"Editra AI Document", "sections":[{"heading":"Source Content", "paragraphs":[source_text[:5000]]}]},
        )
        doc = Document()
        section = doc.sections[0]
        section.top_margin = Inches(.7)
        section.bottom_margin = Inches(.7)
        section.left_margin = Inches(.8)
        section.right_margin = Inches(.8)
        doc.add_heading(content.get("title", "Editra AI Document"), 0)
        for item in content.get("sections", []):
            doc.add_heading(item.get("heading", "Section"), 1)
            for paragraph in item.get("paragraphs", []):
                doc.add_paragraph(paragraph)
        self._polish_layout(doc)
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

    def _insert_generated_section(self, doc, addition):
        doc.add_page_break()
        doc.add_heading(addition.get("heading", "Editra AI Analysis"), 1)
        for text in addition.get("paragraphs", []):
            doc.add_paragraph(text)

    def apply_edit_plan(self, path, plan, source_text=""):
        doc = Document(path)
        for op in plan.get("operations", []):
            kind = op.get("type")
            if kind == "noop":
                continue
            if kind == "replace_paragraph":
                self._replace_paragraph(doc, int(op.get("index", -1)), op.get("text", ""))
            elif kind == "delete_paragraph":
                self._delete_paragraph(doc, int(op.get("index", -1)))
            elif kind == "insert_after_heading":
                self._insert_after_heading(doc, op.get("heading", ""), op.get("paragraphs", []))
            elif kind == "insert_description_at_beginning":
                self._insert_description_at_beginning(doc, source_text)
            elif kind == "append_section":
                doc.add_heading(op.get("heading", "Section"), 1)
                for text in op.get("paragraphs", []):
                    doc.add_paragraph(text)
            elif kind == "replace_table":
                self._replace_table(doc, int(op.get("table_index", -1)), op.get("rows", []))
            elif kind == "add_chart_from_tables":
                self._add_chart_from_table(doc, int(op.get("table_index", -1)), op.get("chart_kind", "bar"), op.get("title", "Chart"), False)
            elif kind == "replace_table_with_chart":
                self._add_chart_from_table(doc, int(op.get("table_index", -1)), op.get("chart_kind", "bar"), op.get("title", "Chart"), True)
            elif kind == "replace_visual_with_table":
                self._restore_table_from_backup(doc, int(op.get("table_index", 0)))
            elif kind == "remove_visuals":
                self._remove_generated_visuals(doc)
        self._polish_layout(doc)
        doc.save(path)
        return path

    def _insert_description_at_beginning(self, doc, source_text):
        # Build a factual, deterministic description from the actual document.
        # This avoids returning an unchanged source file when the LLM is unavailable.
        title = next((p.text.strip() for p in doc.paragraphs if p.text.strip()), "the document")
        headings = [
            p.text.strip() for p in doc.paragraphs
            if p.text.strip() and p.style and p.style.name.startswith("Heading")
        ]
        table_count = len(doc.tables)
        parts = [f"This document, titled '{title}', presents the material contained in the uploaded artifact."]
        if headings:
            parts.append("Its main sections cover " + ", ".join(headings[:8]) + ".")
        if table_count:
            parts.append(f"It also contains {table_count} table" + ("." if table_count == 1 else "s."))
        parts.append("The description is based on the existing document content and preserves the original document below.")

        body = doc._body._element
        first_content = next((child for child in list(body) if child.tag.endswith("}p")), None)
        if first_content is None:
            return False

        heading_el = OxmlElement("w:p")
        body.insert(body.index(first_content), heading_el)
        heading = Paragraph(heading_el, doc.paragraphs[0]._parent)
        heading.style = doc.styles["Heading 1"]
        heading.add_run("Document Description")

        anchor = heading_el
        for text in parts:
            p_el = OxmlElement("w:p")
            anchor.addnext(p_el)
            para = Paragraph(p_el, heading._parent)
            para.style = doc.styles["Normal"]
            para.add_run(text)
            anchor = p_el
        return True

    def _replace_paragraph(self, doc, index, text):
        if 0 <= index < len(doc.paragraphs):
            p = doc.paragraphs[index]
            style = p.style
            p.clear()
            p.style = style
            p.add_run(text)
            return True
        return False

    def _delete_paragraph(self, doc, index):
        if 0 <= index < len(doc.paragraphs):
            p = doc.paragraphs[index]._element
            p.getparent().remove(p)
            return True
        return False

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
                return bool(paragraphs)
        return False

    def _replace_table(self, doc, table_index, rows):
        if not (0 <= table_index < len(doc.tables)):
            return False
        table = doc.tables[table_index]
        while len(table.rows) < len(rows):
            table.add_row()
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                if r < len(table.rows) and c < len(table.rows[r].cells):
                    table.rows[r].cells[c].text = str(value)
        return True

    def _add_chart_from_table(self, doc, table_index, chart_kind, title, replace_table=False):
        if not (0 <= table_index < len(doc.tables)):
            return False
        table = doc.tables[table_index]
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        if len(rows) < 2 or len(rows[0]) < 2:
            return False

        headers = rows[0]
        numeric_col = None
        values, labels = [], []
        for col in range(1, len(headers)):
            cv, cl = [], []
            for row in rows[1:]:
                if col >= len(row):
                    continue
                match = re.search(r"[-+]?\d+(?:\.\d+)?", row[col].replace(",", ""))
                if match:
                    cv.append(float(match.group()))
                    cl.append(row[0] or f"Item {len(cv)}")
            if len(cv) >= 2:
                numeric_col, values, labels = col, cv, cl
                break
        if numeric_col is None:
            return False

        image_path = self._create_chart_image(labels, values, chart_kind, title or headers[numeric_col])
        if not image_path:
            return False

        table_element = table._element
        parent = table_element.getparent()
        index = parent.index(table_element)

        if replace_table:
            backup = OxmlElement("w:p")
            parent.insert(index, backup)
            backup_para = Paragraph(backup, table._parent)
            run = backup_para.add_run(self.BACKUP_PREFIX + json.dumps(rows, ensure_ascii=False))
            run.font.hidden = True
            parent.remove(table_element)
            index += 1
        else:
            index += 1

        image_p = OxmlElement("w:p")
        parent.insert(index, image_p)
        image_para = Paragraph(image_p, table._parent)
        image_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        image_para.add_run().add_picture(image_path, width=Inches(6.1))

        caption_p = OxmlElement("w:p")
        parent.insert(index + 1, caption_p)
        caption = Paragraph(caption_p, table._parent)
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = caption.add_run(f"{self.CHART_CAPTION_PREFIX}{title or 'Chart'}")
        run.bold = True
        run.font.size = Pt(9)

        Path(image_path).unlink(missing_ok=True)
        return True

    def _restore_table_from_backup(self, doc, table_index=0):
        body = doc._body._element
        children = list(body)
        for i, child in enumerate(children):
            text = "".join(child.itertext())
            if self.BACKUP_PREFIX in text:
                raw = text.split(self.BACKUP_PREFIX, 1)[1]
                try:
                    rows = json.loads(raw)
                except Exception:
                    return False

                remove_count = 1
                while i + remove_count < len(children) and remove_count <= 2:
                    sibling = children[i + remove_count]
                    sibling_text = "".join(sibling.itertext())
                    has_drawing = bool(sibling.xpath('.//w:drawing'))
                    if has_drawing or self.CHART_CAPTION_PREFIX in sibling_text:
                        body.remove(sibling)
                        remove_count += 1
                    else:
                        break
                body.remove(child)

                table = doc.add_table(rows=len(rows), cols=max(len(r) for r in rows))
                table.style = "Table Grid"
                for r, values in enumerate(rows):
                    for c, value in enumerate(values):
                        table.cell(r, c).text = str(value)
                table_element = table._element
                body.insert(i, table_element)
                return True
        return False

    def _remove_generated_visuals(self, doc):
        body = doc._body._element
        for child in list(body):
            text = "".join(child.itertext())
            if self.CHART_CAPTION_PREFIX in text:
                siblings = list(body)
                try:
                    idx = siblings.index(child)
                except ValueError:
                    continue
                body.remove(child)
                siblings = list(body)
                if idx > 0 and idx - 1 < len(siblings) and siblings[idx - 1].xpath('.//w:drawing'):
                    body.remove(siblings[idx - 1])
            elif self.BACKUP_PREFIX in text:
                body.remove(child)

    def _create_chart_image(self, labels, values, kind, title):
        try:
            import matplotlib.pyplot as plt
            temp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            temp.close()
            path = temp.name
            fig, ax = plt.subplots(figsize=(8, 4.2))
            if kind == "pie":
                ax.pie(values, labels=labels, autopct="%1.0f%%")
            else:
                ax.bar(labels, values)
                ax.set_ylabel("Value")
                ax.tick_params(axis="x", rotation=25)
            ax.set_title(title)
            fig.tight_layout()
            fig.savefig(path, dpi=180, bbox_inches="tight")
            plt.close(fig)
            return path
        except Exception:
            return None

    def _polish_layout(self, doc):
        """Apply conservative professional alignment without changing content."""
        for section in doc.sections:
            section.top_margin = Inches(.7)
            section.bottom_margin = Inches(.7)
            section.left_margin = Inches(.8)
            section.right_margin = Inches(.8)

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue
            if p.style and p.style.name == "Title":
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif p.style and p.style.name.startswith("Heading"):
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                p.paragraph_format.space_before = Pt(10)
                p.paragraph_format.space_after = Pt(4)
            elif p.style and p.style.name.startswith("List"):
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                p.paragraph_format.space_after = Pt(2)
            elif not any(x in text for x in [self.CHART_CAPTION_PREFIX, self.BACKUP_PREFIX]):
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                p.paragraph_format.space_after = Pt(6)
                p.paragraph_format.line_spacing = 1.08

        for table in doc.tables:
            table.autofit = True
            for row in table.rows:
                for cell in row.cells:
                    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                    for p in cell.paragraphs:
                        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                        p.paragraph_format.space_after = Pt(2)
            if table.rows:
                for cell in table.rows[0].cells:
                    for p in cell.paragraphs:
                        for run in p.runs:
                            run.bold = True
