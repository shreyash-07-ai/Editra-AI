from pathlib import Path
import json
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
from .preview import preview


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

    def _conversation_id(self, current):
        return current.get("conversation_id") if current else uuid.uuid4().hex[:10]

    def _analyze_path(self, raw):
        p = Path(raw)
        if p.suffix.lower() in [".docx", ".pdf", ".png", ".jpg", ".jpeg", ".ppt"]:
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

        return " | ".join(pieces)[:900]

    def run(self, prompt, upload_paths, current_artifact, conversation):
        cid = self._conversation_id(current_artifact)

        # Every follow-up edits the latest generated artifact. Never regenerate
        # from the original upload once a working artifact already exists.
        if current_artifact and Path(current_artifact.get("path", "")).exists():
            current_analysis = self._analyze_path(current_artifact["path"])
            artifact_type = current_artifact.get("artifact_type", "docx")
            plan = self.editing.operation_plan(prompt, artifact_type, current_analysis)
            version = current_artifact.get("version", 0) + 1
            ext = ".pptx" if artifact_type == "pptx" else ".docx"
            aid, output_path = self.store.new_output(ext, version)
            if artifact_type == "pptx":
                self.ppt_gen.generate(
                    output_path,
                    prompt,
                    self._source_text([current_analysis]),
                    existing=current_artifact,
                    edit_plan=plan,
                )
            else:
                self.doc_gen.generate(
                    output_path,
                    prompt,
                    self._source_text([current_analysis]),
                    existing=current_artifact,
                    edit_plan=plan,
                )
            return self._finalize(
                aid, output_path, artifact_type, version, cid, current_analysis, []
            )

        # First request: when the user uploads an editable DOCX/PPTX, the
        # uploaded file itself is the working document. We copy it once and
        # apply the prompt as a minimal edit plan. We do NOT append a separate
        # AI-generated document to the source. This is the key document-editing
        # contract: input document -> prompt -> updated version of that document.
        editable_upload = next(
            (
                p for p in upload_paths
                if Path(p).suffix.lower() in {".docx", ".pptx"}
            ),
            None,
        )
        if editable_upload:
            raw_path = Path(editable_upload)
            analysis = self._analyze_path(raw_path)
            artifact_type = "pptx" if raw_path.suffix.lower() == ".pptx" else "docx"
            plan = self.editing.operation_plan(prompt, artifact_type, analysis)
            aid, output_path = self.store.new_output(
                ".pptx" if artifact_type == "pptx" else ".docx", 1
            )

            if artifact_type == "pptx":
                self.ppt_gen.generate(
                    output_path,
                    prompt,
                    self._source_text([analysis]),
                    template_path=str(raw_path),
                    edit_plan=plan,
                )
            else:
                self.doc_gen.generate(
                    output_path,
                    prompt,
                    self._source_text([analysis]),
                    template_path=str(raw_path),
                    edit_plan=plan,
                )

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

        route = self.supervisor.route(prompt, None, analyses)
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
        aid, output_path = self.store.new_output(
            ".pptx" if artifact_type == "pptx" else ".docx", 1
        )
        if artifact_type == "pptx":
            self.ppt_gen.generate(
                output_path,
                route["instructions"],
                source_text,
                template_path=template_path,
            )
        else:
            self.doc_gen.generate(
                output_path,
                route["instructions"],
                source_text,
                template_path=None,
            )
        return self._finalize(
            aid,
            output_path,
            artifact_type,
            1,
            cid,
            analyses[0] if analyses else {},
            sources,
        )

    def _finalize(self, aid, output_path, artifact_type, version, cid, structure, sources):
        ok, checks = self.validation.validate(output_path, artifact_type)
        if not ok:
            return {
                "message": "I generated the artifact, but validation failed: "
                + "; ".join(checks)
            }
        pdir = self.store.preview_dir(aid)
        images = preview(output_path, artifact_type, pdir)
        artifact = {
            "id": aid,
            "conversation_id": cid,
            "filename": output_path.name,
            "path": str(output_path),
            "artifact_type": artifact_type,
            "version": version,
            "mime": (
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                if artifact_type == "pptx"
                else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            "preview_type": "images" if images else "text",
            "preview": images
            if images
            else "Preview unavailable. Install LibreOffice for visual DOCX/PPTX previews.",
            "structure": structure,
            "sources": sources,
        }
        self.store.register(artifact)
        message = (
            f"Done — I created **{artifact['filename']}** (version {version}). "
            "The next edit will modify only the requested part and preserve the rest of this artifact."
        )
        return {"message": message, "artifact": artifact, "sources": sources}
