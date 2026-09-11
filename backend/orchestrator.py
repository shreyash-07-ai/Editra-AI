from pathlib import Path
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
from .config import OUTPUT_DIR

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

    def run(self, prompt, upload_paths, current_artifact, conversation):
        cid = self._conversation_id(current_artifact)
        analyses = []
        source_text = ""
        template_path = None

        for raw in upload_paths:
            p = Path(raw)
            try:
                a = self.doc_agent.analyze(p) if p.suffix.lower() in [".docx",".pdf",".png",".jpg",".jpeg"] else self.ppt_agent.analyze(p)
                analyses.append(a)
                if a.get("type") == "docx":
                    source_text += "\n".join(a.get("paragraphs", []))
                elif a.get("type") == "pdf":
                    source_text += "\n".join(a.get("pages", []))
                elif a.get("type") == "pptx":
                    for s in a.get("slides", []):
                        source_text += "\n".join(x["text"] for x in s.get("items", []))
                    template_path = str(p)
            except Exception as e:
                analyses.append({"error":str(e)})

        route = self.supervisor.route(prompt, current_artifact, analyses)

        sources = []
        if route.get("research"):
            rr = self.research.search(prompt)
            for x in rr.get("results", []):
                source_text += f"\n{x.get('title')}: {x.get('content')}"
                if x.get("url"): sources.append(x["url"])

        if route.get("rag"):
            for x in self.rag.retrieve(prompt):
                source_text += "\n" + str(x)
                if x.get("source"): sources.append(str(x["source"]))

        artifact_type = route.get("output_type") or (current_artifact or {}).get("artifact_type","docx")
        version = (current_artifact.get("version",0) + 1) if current_artifact else 1

        if current_artifact and Path(current_artifact["path"]).exists():
            # Use the previous artifact itself as the editing source.
            source_text += "\nCURRENT ARTIFACT:\n" + str(current_artifact.get("structure", {}))

        ext = ".pptx" if artifact_type == "pptx" else ".docx"
        aid, output_path = self.store.new_output(ext, version)

        if artifact_type == "pptx":
            self.ppt_gen.generate(
                output_path, route["instructions"], source_text,
                template_path=template_path if not current_artifact else None,
                existing=current_artifact
            )
        else:
            self.doc_gen.generate(
                output_path, route["instructions"], source_text,
                existing=current_artifact
            )

        ok, checks = self.validation.validate(output_path, artifact_type)
        if not ok:
            return {"message":"I generated the artifact, but validation failed: " + "; ".join(checks)}

        pdir = self.store.preview_dir(aid)
        images = preview(output_path, artifact_type, pdir)

        artifact = {
            "id": aid,
            "conversation_id": cid,
            "filename": output_path.name,
            "path": str(output_path),
            "artifact_type": artifact_type,
            "version": version,
            "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation" if artifact_type=="pptx" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "preview_type": "images" if images else "text",
            "preview": images if images else "Preview unavailable. Install LibreOffice for visual DOCX/PPTX previews.",
            "structure": analyses[0] if analyses else {},
            "sources": sources
        }
        self.store.register(artifact)

        message = f"Done — I created **{artifact['filename']}** (version {version}). You can preview it above and download the editable file. You can now give me another instruction and I’ll create the next version."
        return {"message":message, "artifact":artifact, "sources":sources}
