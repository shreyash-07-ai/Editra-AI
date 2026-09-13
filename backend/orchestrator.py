from pathlib import Path
import json
import shutil
import uuid

from .agents.supervisor_agent import SupervisorAgent
from .agents.document_agent import DocumentAgent
from .agents.ppt_agent import PPTAgent
from .agents.research_agent import ResearchAgent
from .agents.rag_agent import RAGAgent
from .agents.validation_agent import ValidationAgent
from .agents.editing_agent import EditingAgent
from .generators.docx_generator import DOCXGenerator
from .generators.pptx_generator import PPTXGenerator
from .generators.xlsx_generator import XLSXGenerator
from .preview import preview, convert_to_pdf
from .storage import MIME

EDITABLE_TYPES = {"docx", "pptx", "xlsx"}


class EditraOrchestrator:
    def __init__(self, store):
        self.store = store
        self.supervisor = SupervisorAgent()
        self.doc_agent = DocumentAgent()
        self.ppt_agent = PPTAgent()
        self.research = ResearchAgent()
        self.rag = RAGAgent()
        self.validation = ValidationAgent()
        self.editing = EditingAgent()
        self.doc_gen = DOCXGenerator()
        self.ppt_gen = PPTXGenerator()
        self.xlsx_gen = XLSXGenerator()

    def _conversation_id(self, current):
        return current.get("conversation_id") if current else uuid.uuid4().hex[:10]

    def _analyze_path(self, raw):
        p = Path(raw)
        if p.suffix.lower() in [".docx", ".pdf", ".png", ".jpg", ".jpeg", ".ppt", ".xlsx", ".csv"]:
            return self.doc_agent.analyze(p)
        return self.ppt_agent.analyze(p)

    def _source_text(self, analyses):
        chunks = []
        for a in analyses:
            kind = a.get("type")
            if kind == "docx":
                for p in a.get("paragraphs", []):
                    chunks.append(p.get("text", "") if isinstance(p, dict) else str(p))
                for t in a.get("tables", []):
                    chunks.append("TABLE: " + json.dumps(t.get("rows", t)))
            elif kind == "pdf":
                for p in a.get("pages", []):
                    chunks.append(p.get("text", "") if isinstance(p, dict) else str(p))
            elif kind == "pptx":
                for s in a.get("slides", []):
                    chunks.append(
                        f"SLIDE {s.get('number')}: "
                        + " | ".join(x.get("text", "") for x in s.get("items", []))
                    )
            elif kind == "image":
                chunks.append(a.get("ocr_text", ""))
            elif kind in ("xlsx", "csv"):
                for sheet in a.get("sheets", []):
                    chunks.append(f"SHEET {sheet.get('name')}: headers=" + json.dumps(sheet.get("headers", [])))
                    for row in sheet.get("rows", [])[:30]:
                        chunks.append("ROW: " + json.dumps(row))
        return "\n".join(x for x in chunks if x).strip()

    def _research_context(self, analyses):
        """Build a compact topic-oriented context for web search."""
        pieces = []
        for analysis in analyses:
            kind = analysis.get("type")
            if kind == "docx":
                paragraphs = analysis.get("paragraphs", [])
                for item in paragraphs:
                    text = item.get("text", "") if isinstance(item, dict) else str(item)
                    if text.strip():
                        pieces.append(text.strip())
                    if len(pieces) >= 12:
                        break
            elif kind == "pptx":
                for slide in analysis.get("slides", []):
                    texts = [x.get("text", "") for x in slide.get("items", [])]
                    if texts:
                        pieces.append("Slide " + str(slide.get("number")) + ": " + " | ".join(texts[:2]))
                    if len(pieces) >= 12:
                        break
            elif kind == "pdf":
                for page in analysis.get("pages", [])[:4]:
                    text = page.get("text", "")
                    if text.strip():
                        pieces.append(text.strip()[:300])
            elif kind == "image":
                text = analysis.get("ocr_text", "")
                if text.strip():
                    pieces.append(text.strip()[:500])
            elif kind in ("xlsx", "csv"):
                for sheet in analysis.get("sheets", [])[:3]:
                    pieces.append("Sheet " + str(sheet.get("name")) + ": " + json.dumps(sheet.get("headers", [])))

        return " | ".join(pieces)[:900]

    def _effective_working_artifact(self, current_artifact):
        """Resolve the artifact that further structural edits should target.

        A PDF/CSV export is a leaf output, not a new editable state: it keeps a
        pointer (``editable_source``) back to the DOCX/PPTX/XLSX it was derived
        from, so a later instruction like "change the font size" still lands on
        the correct working document instead of the flattened export.
        """
        if not current_artifact:
            return None
        if current_artifact.get("artifact_type") in EDITABLE_TYPES:
            return current_artifact
        return current_artifact.get("editable_source")

    def _is_undo_request(self, prompt_lower):
        if prompt_lower in {"undo", "undo last", "undo that"}:
            return True
        return any(
            k in prompt_lower
            for k in ["undo the last change", "undo last change", "undo the last edit",
                      "undo last edit", "undo that change", "undo it", "revert the last change",
                      "revert last change"]
        )

    def _is_restore_original_request(self, prompt_lower):
        return "original" in prompt_lower and any(
            k in prompt_lower for k in ["go back", "restore", "revert", "back to"]
        )

    def _detect_target_format(self, prompt_lower, current_type):
        conversion_verbs = [
            "convert", "export", "save as", "give me a", "give me an", "make it a",
            "make it an", "now make it", "turn this into", "turn it into",
            "generate a", "create a", "as a pdf", "as pdf",
        ]
        has_verb = any(v in prompt_lower for v in conversion_verbs)
        fmt = None
        if "pdf" in prompt_lower:
            fmt = "pdf"
        elif any(k in prompt_lower for k in ["pptx", "powerpoint", "presentation", "slide deck"]):
            fmt = "pptx"
        elif any(k in prompt_lower for k in ["docx", "word document"]):
            fmt = "docx"
        elif any(k in prompt_lower for k in ["xlsx", "excel", "spreadsheet"]):
            fmt = "xlsx"
        elif "csv" in prompt_lower:
            fmt = "csv"

        if not fmt or fmt == current_type:
            return None
        # A plain PDF mention is unambiguous (nothing else ends in "pdf"); the
        # other targets require an explicit conversion verb to avoid treating
        # ordinary edit prompts ("make the word count shorter") as conversions.
        if fmt == "pdf" or has_verb:
            return fmt
        return None

    def _handle_undo(self, current_artifact, cid):
        versions = self.store.versions(cid)
        target_version = current_artifact.get("version", 1) - 1
        previous = next((v for v in versions if v.get("version") == target_version), None)
        if target_version < 1 or not previous:
            return {"message": "There's no earlier version to undo to."}
        return {
            "message": f"Reverted to version {previous['version']} — **{previous['filename']}**. "
            "The next edit will apply to this version.",
            "artifact": previous,
            "sources": previous.get("sources", []),
        }

    def _handle_restore_original(self, current_artifact, cid):
        original = self.store.original_path(cid)
        if not original or not Path(original).exists():
            return {"message": "I don't have the original uploaded file saved for this conversation anymore."}
        original = Path(original)
        suffix = original.suffix.lower()
        version = current_artifact.get("version", 0) + 1

        if suffix == ".csv":
            # Restore into the same normalized, editable XLSX shape used on
            # first upload, so continued editing keeps working afterward.
            aid, output_path = self.store.new_output(".xlsx", version)
            self.xlsx_gen.generate(output_path, "", "", template_path=str(original))
            analysis = self._analyze_path(output_path)
            return self._finalize(aid, output_path, "xlsx", version, cid, analysis, [original.name])

        if suffix in (".docx", ".pptx", ".xlsx"):
            artifact_type = "pptx" if suffix == ".pptx" else ("xlsx" if suffix == ".xlsx" else "docx")
            aid, output_path = self.store.new_output(suffix, version)
            shutil.copy2(original, output_path)
            analysis = self._analyze_path(output_path)
            return self._finalize(aid, output_path, artifact_type, version, cid, analysis, [original.name])

        # Non-editable original (PDF/image/other): hand back the raw file as a
        # snapshot; it isn't a new editable state.
        try:
            analysis = self._analyze_path(original)
        except Exception:
            analysis = {}
        aid, output_path = self.store.new_output(suffix, version)
        shutil.copy2(original, output_path)
        artifact = {
            "id": aid, "conversation_id": cid, "filename": output_path.name, "path": str(output_path),
            "artifact_type": suffix.lstrip("."), "version": version,
            "mime": MIME.get(suffix, "application/octet-stream"),
            "preview_type": "text", "preview": "Restored the original uploaded file.",
            "structure": analysis, "sources": [original.name],
        }
        self.store.register(artifact)
        return {"message": f"Restored the original file — **{artifact['filename']}**.", "artifact": artifact, "sources": [original.name]}

    def _export_pdf(self, working, cid, version):
        aid, output_path = self.store.new_output(".pdf", version)
        if not convert_to_pdf(working["path"], output_path):
            return {
                "message": "I couldn't generate a PDF because LibreOffice isn't available in this "
                "environment. The editable version is still ready to download; install LibreOffice "
                "(`soffice` on PATH) to enable PDF export."
            }
        ok, checks = self.validation.validate(output_path, "pdf")
        if not ok:
            return {"message": "I generated the PDF, but validation failed: " + "; ".join(checks)}
        artifact = {
            "id": aid, "conversation_id": cid, "filename": output_path.name, "path": str(output_path),
            "artifact_type": "pdf", "version": version, "mime": MIME.get(".pdf"),
            "preview_type": "text", "preview": "PDF export of the current version.",
            "structure": working.get("structure", {}), "sources": working.get("sources", []),
            "editable_source": working,
        }
        self.store.register(artifact)
        return {
            "message": f"Done — I exported the current version as **{artifact['filename']}** "
            f"(version {version}). Further edits will keep applying to the editable "
            f"{working['artifact_type'].upper()}.",
            "artifact": artifact,
            "sources": artifact["sources"],
        }

    def _export_csv(self, working, cid, version):
        if working.get("artifact_type") != "xlsx":
            return {"message": "CSV export is only available from a spreadsheet (XLSX) artifact."}
        aid, output_path = self.store.new_output(".csv", version)
        try:
            self.xlsx_gen.export_csv(working["path"], output_path)
        except Exception as exc:
            return {"message": f"I couldn't export to CSV: {exc}"}
        ok, checks = self.validation.validate(output_path, "csv")
        if not ok:
            return {"message": "I generated the CSV, but validation failed: " + "; ".join(checks)}
        artifact = {
            "id": aid, "conversation_id": cid, "filename": output_path.name, "path": str(output_path),
            "artifact_type": "csv", "version": version, "mime": MIME.get(".csv"),
            "preview_type": "text", "preview": "CSV export of the current version.",
            "structure": working.get("structure", {}), "sources": working.get("sources", []),
            "editable_source": working,
        }
        self.store.register(artifact)
        return {
            "message": f"Done — I exported the current version as **{artifact['filename']}** (version {version}).",
            "artifact": artifact,
            "sources": artifact["sources"],
        }

    def _is_noop_plan(self, plan):
        ops = plan.get("operations", []) if isinstance(plan, dict) else []
        return bool(ops) and all(op.get("type") == "noop" for op in ops)

    def _noop_message(self, artifact_type):
        hint = {
            "pptx": "the exact slide number, its title, or the text on it",
            "xlsx": "the exact sheet name, cell, or column",
        }.get(artifact_type, "the exact heading, sentence, or section")
        return (
            "I couldn't confidently identify a specific, safe edit for that request without risking "
            f"unrelated changes. Could you point to {hint} you'd like changed? "
            "Your current version is unchanged."
        )

    def _handle_format_export(self, prompt_lower, prompt, current_artifact, cid):
        working = self._effective_working_artifact(current_artifact)
        if not working or not Path(working.get("path", "")).exists():
            return None
        target = self._detect_target_format(prompt_lower, working.get("artifact_type"))
        if not target:
            return None

        version = current_artifact.get("version", working.get("version", 0)) + 1

        if target == "pdf":
            return self._export_pdf(working, cid, version)

        if target == "csv":
            return self._export_csv(working, cid, version)

        # Structural conversion between editable formats (docx <-> pptx <-> xlsx).
        try:
            analysis = self._analyze_path(Path(working["path"]))
            source_text = self._source_text([analysis])
            aid, output_path = self.store.new_output(f".{target}", version)
            if target == "pptx":
                self.ppt_gen.generate(output_path, prompt, source_text)
            elif target == "xlsx":
                self.xlsx_gen.generate(output_path, prompt, source_text)
            else:
                self.doc_gen.generate(output_path, prompt, source_text)
        except Exception as exc:
            return {"message": f"I couldn't convert the current version to {target.upper()}: {exc} "
                    f"Your current {working.get('artifact_type', '').upper()} version is unchanged."}
        return self._finalize(aid, output_path, target, version, cid, analysis, working.get("sources", []))

    def run(self, prompt, upload_paths, current_artifact, conversation):
        cid = self._conversation_id(current_artifact)
        prompt_lower = (prompt or "").lower().strip()

        if current_artifact and self._is_undo_request(prompt_lower):
            return self._handle_undo(current_artifact, cid)

        if current_artifact and self._is_restore_original_request(prompt_lower):
            return self._handle_restore_original(current_artifact, cid)

        if current_artifact:
            export_result = self._handle_format_export(prompt_lower, prompt, current_artifact, cid)
            if export_result:
                return export_result

        # Every follow-up edits the latest generated editable artifact. Never
        # regenerate from the original upload once a working artifact already
        # exists, and never try to structurally edit a flattened PDF/CSV export
        # directly (resolve back to the editable source it came from instead).
        working = self._effective_working_artifact(current_artifact)
        if working and Path(working.get("path", "")).exists():
            try:
                current_analysis = self._analyze_path(working["path"])
            except Exception as exc:
                return {"message": f"I couldn't read the current version to edit it: {exc}. "
                        "Your existing version is unchanged."}
            artifact_type = working.get("artifact_type", "docx")
            try:
                plan = self.editing.operation_plan(prompt, artifact_type, current_analysis)
            except Exception as exc:
                return {"message": f"I couldn't analyze that edit request: {exc} "
                        "Your current version is unchanged."}
            if self._is_noop_plan(plan):
                return {"message": self._noop_message(artifact_type)}
            version = current_artifact.get("version", 0) + 1
            ext = {"pptx": ".pptx", "xlsx": ".xlsx"}.get(artifact_type, ".docx")
            aid, output_path = self.store.new_output(ext, version)
            source_text = self._source_text([current_analysis])
            try:
                if artifact_type == "pptx":
                    self.ppt_gen.generate(output_path, prompt, source_text, existing=working, edit_plan=plan)
                elif artifact_type == "xlsx":
                    self.xlsx_gen.generate(output_path, prompt, source_text, existing=working, edit_plan=plan)
                else:
                    self.doc_gen.generate(output_path, prompt, source_text, existing=working, edit_plan=plan)
            except Exception as exc:
                return {"message": f"I couldn't apply that change safely: {exc} "
                        f"Your current version (v{working.get('version')}) is unchanged."}
            return self._finalize(
                aid, output_path, artifact_type, version, cid, current_analysis, []
            )

        # First request: when the user uploads an editable DOCX/PPTX/XLSX (or a
        # CSV, normalized into XLSX), the uploaded file itself is the working
        # document. We copy it once and apply the prompt as a minimal edit plan.
        # We do NOT append a separate AI-generated document to the source. This
        # is the key document-editing contract: input document -> prompt ->
        # updated version of that document.
        editable_upload = next(
            (
                p for p in upload_paths
                if Path(p).suffix.lower() in {".docx", ".pptx", ".xlsx", ".csv"}
            ),
            None,
        )
        if editable_upload:
            raw_path = Path(editable_upload)
            try:
                analysis = self._analyze_path(raw_path)
            except Exception as exc:
                return {"message": f"I couldn't read '{raw_path.name}': {exc}. "
                        "It may be corrupted or in an unsupported layout. Please try another file."}
            self.store.set_original(cid, raw_path)
            suffix = raw_path.suffix.lower()
            if suffix == ".pptx":
                source_type = "pptx"
            elif suffix in (".xlsx", ".csv"):
                source_type = "xlsx"
            else:
                source_type = "docx"

            # Honor an explicit target format in the very first prompt too, e.g.
            # uploading a DOCX and asking to "convert this into a PowerPoint" or
            # "make this a PPT" — not just on later follow-up prompts.
            requested_format = self._detect_target_format(prompt_lower, source_type)
            source_text = self._source_text([analysis])

            if requested_format and requested_format in EDITABLE_TYPES and requested_format != source_type:
                ext = f".{requested_format}"
                aid, output_path = self.store.new_output(ext, 1)
                try:
                    if requested_format == "pptx":
                        self.ppt_gen.generate(output_path, prompt, source_text)
                    elif requested_format == "xlsx":
                        self.xlsx_gen.generate(output_path, prompt, source_text)
                    else:
                        self.doc_gen.generate(output_path, prompt, source_text)
                except Exception as exc:
                    return {"message": f"I couldn't convert '{raw_path.name}' to {requested_format.upper()}: {exc}"}
                return self._finalize(aid, output_path, requested_format, 1, cid, analysis, [raw_path.name])

            if requested_format in ("pdf", "csv"):
                # First message asks to directly export the upload (e.g. "give me
                # a PDF of this resume"): register the upload itself as v1, then
                # export it as v2 so future edits still target the editable v1.
                ext = {"pptx": ".pptx", "xlsx": ".xlsx"}.get(source_type, ".docx")
                aid1, output_path1 = self.store.new_output(ext, 1)
                if suffix == ".csv":
                    self.xlsx_gen.generate(output_path1, "", "", template_path=str(raw_path))
                else:
                    shutil.copy2(raw_path, output_path1)
                v1 = self._finalize(aid1, output_path1, source_type, 1, cid, analysis, [raw_path.name])
                if not v1.get("artifact"):
                    return v1
                working = v1["artifact"]
                export = self._export_pdf(working, cid, 2) if requested_format == "pdf" else self._export_csv(working, cid, 2)
                return export

            artifact_type = source_type
            try:
                plan = self.editing.operation_plan(prompt, artifact_type, analysis)
            except Exception as exc:
                return {"message": f"I couldn't analyze that edit request: {exc}"}
            if self._is_noop_plan(plan):
                return {"message": self._noop_message(artifact_type)}
            ext = {"pptx": ".pptx", "xlsx": ".xlsx"}.get(artifact_type, ".docx")
            aid, output_path = self.store.new_output(ext, 1)

            try:
                if artifact_type == "pptx":
                    self.ppt_gen.generate(output_path, prompt, source_text, template_path=str(raw_path), edit_plan=plan)
                elif artifact_type == "xlsx":
                    self.xlsx_gen.generate(output_path, prompt, source_text, template_path=str(raw_path), edit_plan=plan)
                else:
                    self.doc_gen.generate(output_path, prompt, source_text, template_path=str(raw_path), edit_plan=plan)
            except Exception as exc:
                return {"message": f"I couldn't apply that change safely: {exc} "
                        "Try rephrasing the request, or ask for a different edit."}

            return self._finalize(
                aid,
                output_path,
                artifact_type,
                1,
                cid,
                analysis,
                [raw_path.name],
            )

        # Non-editable inputs (PDF/images) still use the existing generation
        # flow to create an editable DOCX, while subsequent prompts edit that
        # generated artifact instead of returning the source again.
        if upload_paths:
            self.store.set_original(cid, upload_paths[0])
        analyses = []
        source_text = ""
        template_path = None
        for raw in upload_paths:
            p = Path(raw)
            try:
                a = self._analyze_path(p)
                analyses.append(a)
                source_text += "\n" + self._source_text([a])
                if a.get("type") == "pptx":
                    template_path = str(p)
            except Exception as e:
                analyses.append({"error": str(e), "path": str(p)})
        source_text = source_text.strip()

        if upload_paths and analyses and all(a.get("error") for a in analyses):
            failures = "; ".join(f"{Path(a['path']).name}: {a['error']}" for a in analyses)
            return {"message": f"I couldn't read the uploaded file(s): {failures}. "
                    "They may be corrupted or in an unsupported format."}

        try:
            route = self.supervisor.route(prompt, None, analyses)
        except Exception as exc:
            return {"message": f"I couldn't analyze that request: {exc}"}
        sources = [Path(x).name for x in upload_paths]

        if upload_paths or route.get("research"):
            research_context = self._research_context(analyses)
            research_query = (prompt or "").strip()
            if research_context:
                research_query += "\nRelated document topics: " + research_context
            rr = self.research.search(research_query)
            for x in rr.get("results", []):
                source_text += f"\nWEB SOURCE: {x.get('title', '')}\n{x.get('content', '')}"
                if x.get("url"):
                    sources.append(x["url"])

        if route.get("rag"):
            for x in self.rag.retrieve(prompt):
                source_text += "\nRAG SOURCE: " + str(x)
                if x.get("source"):
                    sources.append(str(x["source"]))

        artifact_type = route.get("output_type") or (
            "pptx" if any(x.get("type") == "pptx" for x in analyses) else "docx"
        )
        ext = {"pptx": ".pptx", "xlsx": ".xlsx"}.get(artifact_type, ".docx")
        aid, output_path = self.store.new_output(ext, 1)
        try:
            if artifact_type == "pptx":
                self.ppt_gen.generate(
                    output_path,
                    route["instructions"],
                    source_text,
                    template_path=template_path,
                )
            elif artifact_type == "xlsx":
                self.xlsx_gen.generate(
                    output_path,
                    route["instructions"],
                    source_text,
                )
            else:
                self.doc_gen.generate(
                    output_path,
                    route["instructions"],
                    source_text,
                    template_path=None,
                )
        except Exception as exc:
            return {"message": f"I couldn't generate the artifact: {exc}"}
        return self._finalize(
            aid,
            output_path,
            artifact_type,
            1,
            cid,
            analyses[0] if analyses else {},
            sources,
        )

    def _text_preview(self, artifact_type):
        if artifact_type == "xlsx":
            return "Preview unavailable for spreadsheets in this UI. Download the file to view it."
        if artifact_type == "csv":
            return "CSV export ready for download."
        if artifact_type == "pdf":
            return "PDF export ready for download."
        return "Preview unavailable. Install LibreOffice for visual DOCX/PPTX previews."

    def _finalize(self, aid, output_path, artifact_type, version, cid, structure, sources):
        ok, checks = self.validation.validate(output_path, artifact_type)
        if not ok:
            return {
                "message": "I generated the artifact, but validation failed: "
                + "; ".join(checks)
            }
        pdir = self.store.preview_dir(aid)
        images = preview(output_path, artifact_type, pdir) if artifact_type in ("docx", "pptx") else []
        ext = Path(output_path).suffix.lower()
        artifact = {
            "id": aid,
            "conversation_id": cid,
            "filename": output_path.name,
            "path": str(output_path),
            "artifact_type": artifact_type,
            "version": version,
            "mime": MIME.get(ext, "application/octet-stream"),
            "preview_type": "images" if images else "text",
            "preview": images if images else self._text_preview(artifact_type),
            "structure": structure,
            "sources": sources,
        }
        self.store.register(artifact)
        message = (
            f"Done — I created **{artifact['filename']}** (version {version}). "
            "The next edit will modify only the requested part and preserve the rest of this artifact."
        )
        return {"message": message, "artifact": artifact, "sources": sources}
