from copy import deepcopy
from pathlib import Path
import shutil
import re
import tempfile

from docx import Document
from docx.shared import Inches
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph

from ..llm import LLM


class DOCXGenerator:
    def __init__(self):
        self.llm = LLM()

    def generate(self, output_path, prompt, source_text="", existing=None, template_path=None, edit_plan=None):
        base = existing.get("path") if existing else template_path
        if base and Path(base).exists():
            shutil.copy2(base, output_path)
            if edit_plan:
                return self.apply_edit_plan(output_path, edit_plan)
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
        changed = False

        for op in plan.get("operations", []):
            kind = op.get("type")
            if kind == "replace_paragraph":
                changed |= self._replace_paragraph(doc, int(op.get("index", -1)), op.get("text", ""))
            elif kind == "delete_paragraph":
                changed |= self._delete_paragraph(doc, int(op.get("index", -1)))
            elif kind == "insert_after_heading":
                changed |= self._insert_after_heading(doc, op.get("heading", ""), op.get("paragraphs", []))
            elif kind == "append_section":
                doc.add_heading(op.get("heading", "Section"), 1)
                for text in op.get("paragraphs", []):
                    doc.add_paragraph(text)
                changed = True
            elif kind == "replace_table":
                changed |= self._replace_table(doc, int(op.get("table_index", -1)), op.get("rows", []))
            elif kind == "add_chart_from_tables":
                changed |= self._add_chart_from_table(
                    doc,
                    int(op.get("table_index", -1)),
                    op.get("chart_kind", "bar"),
                    op.get("title", "Chart"),
                    replace_table=False,
                )
            elif kind == "replace_table_with_chart":
                changed |= self._add_chart_from_table(
                    doc,
                    int(op.get("table_index", -1)),
                    op.get("chart_kind", "bar"),
                    op.get("title", "Chart"),
                    replace_table=True,
                )

        # Never silently create an identical version when an edit plan had a
        # non-noop operation. The caller still gets a valid artifact, but this
        # makes visual requests actually modify the document.
        doc.save(path)
        return path

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
            if r >= len(table.rows):
                break
            for c, value in enumerate(values):
                if c < len(table.rows[r].cells):
                    table.rows[r].cells[c].text = str(value)
        return True

    def _add_chart_from_table(self, doc, table_index, chart_kind, title, replace_table=False):
        if not (0 <= table_index < len(doc.tables)):
            return False

        table = doc.tables[table_index]
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        if len(rows) < 2 or len(rows[0]) < 2:
            return False

        # Find one numeric column. For an implementation-plan table this is
        # typically the duration/week/percentage column. We deliberately use
        # only numbers already present in the source table.
        headers = rows[0]
        numeric_col = None
        values = []
        labels = []
        for col in range(1, len(headers)):
            candidate_values = []
            candidate_labels = []
            for row in rows[1:]:
                if col >= len(row):
                    continue
                match = re.search(r"[-+]?\d+(?:\.\d+)?", row[col].replace(",", ""))
                if match:
                    candidate_values.append(float(match.group()))
                    candidate_labels.append(row[0] if row else f"Item {len(candidate_values)}")
            if len(candidate_values) >= 2:
                numeric_col = col
                values = candidate_values
                labels = candidate_labels
                break

        if numeric_col is None:
            return False

        image_path = self._create_chart_image(
            labels,
            values,
            chart_kind,
            title or headers[numeric_col],
        )
        if not image_path:
            return False

        if replace_table:
            table_element = table._element
            parent = table_element.getparent()
            index = parent.index(table_element)
            parent.remove(table_element)

            # Insert chart immediately where the table was.
            p = OxmlElement("w:p")
            parent.insert(index, p)
            para = Paragraph(p, table._parent)
            para.add_run().add_picture(image_path, width=Inches(6.3))
            caption = OxmlElement("w:p")
            parent.insert(index + 1, caption)
            cap_para = Paragraph(caption, table._parent)
            cap_run = cap_para.add_run(title or "Chart")
            cap_run.bold = True
        else:
            doc.add_paragraph(title or "Chart").runs[0].bold = True
            doc.add_picture(image_path, width=Inches(6.3))

        try:
            Path(image_path).unlink(missing_ok=True)
        except Exception:
            pass
        return True

    def _create_chart_image(self, labels, values, kind, title):
        try:
            import matplotlib.pyplot as plt

            temp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            temp.close()
            path = temp.name

            fig, ax = plt.subplots(figsize=(8, 4.5))
            if kind == "pie":
                ax.pie(values, labels=labels, autopct="%1.0f%%")
            else:
                ax.bar(labels, values)
                ax.set_ylabel("Value")
                ax.tick_params(axis="x", rotation=30)
            ax.set_title(title)
            fig.tight_layout()
            fig.savefig(path, dpi=180, bbox_inches="tight")
            plt.close(fig)
            return path
        except Exception:
            return None
