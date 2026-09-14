import streamlit as st
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.orchestrator import EditraOrchestrator
from backend.query_pipeline import QueryDrivenPipeline
from backend.storage import ArtifactStore

st.set_page_config(page_title="Editra AI", page_icon="✦", layout="wide")
css = Path(__file__).with_name("ui_theme_v2.css")
if css.exists():
    st.markdown(f"<style>{css.read_text()}</style>", unsafe_allow_html=True)

if "store" not in st.session_state: st.session_state.store = ArtifactStore()
if "orch" not in st.session_state: st.session_state.orch = EditraOrchestrator(st.session_state.store)
if "query_pipeline" not in st.session_state: st.session_state.query_pipeline = QueryDrivenPipeline(st.session_state.store)
if "messages" not in st.session_state: st.session_state.messages = []
if "current_artifact" not in st.session_state: st.session_state.current_artifact = None

with st.sidebar:
    st.markdown('<div class="editra-brand">✦ Editra <span>AI</span></div>', unsafe_allow_html=True)
    st.caption("Your AI document editor")
    if st.button("＋ New chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.current_artifact = None
        st.session_state.pop("upload_paths", None)
        st.rerun()
    st.divider()
    st.markdown("**Source document**")
    st.caption("PDF, DOCX, PPTX, PPT, XLSX, CSV, PNG, JPG, JPEG")
    uploads = st.file_uploader("Choose source file", type=["docx","pdf","pptx","ppt","xlsx","csv","png","jpg","jpeg"], accept_multiple_files=True)
    if uploads:
        st.session_state.upload_paths = [str(st.session_state.store.save_upload(x.name, x.getvalue())) for x in uploads]
        st.success(f"{len(uploads)} file(s) ready")
    st.divider()
    st.markdown("**Capabilities**")
    for item in ["Extraction + semantic chunking", "Gemini embeddings + Pinecone RAG", "Query-driven analysis", "Optional web research", "Editable PDF / PPT / DOCX / TXT", "Conversational editing + versioning"]:
        st.caption(f"• {item}")

st.markdown('<div class="editra-badge">✦ AI-Powered Document Editing</div>', unsafe_allow_html=True)
st.markdown('<div class="editra-title">Create with your <span>documents</span></div>', unsafe_allow_html=True)
st.markdown('<div class="editra-subtitle">Upload a document and tell Editra what you need. Get an editable file in seconds.</div>', unsafe_allow_html=True)

if not st.session_state.current_artifact:
    st.markdown('<div class="workspace-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">1. Upload your document</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Add the source material Editra should use as evidence.</div>', unsafe_allow_html=True)
    up, files = st.columns([1.6, 1], gap="large")
    with up:
        main_uploads = st.file_uploader("Drag and drop or browse", type=["docx","pdf","pptx","ppt","xlsx","csv","png","jpg","jpeg"], accept_multiple_files=True, label_visibility="collapsed", key="main_uploader")
        if main_uploads:
            st.session_state.upload_paths = [str(st.session_state.store.save_upload(x.name, x.getvalue())) for x in main_uploads]
            st.success(f"{len(main_uploads)} source file(s) ready")
    with files:
        paths = getattr(st.session_state, "upload_paths", [])
        if paths:
            st.markdown('<div class="file-panel-title">Uploaded files</div>', unsafe_allow_html=True)
            for path in paths:
                st.markdown(f'<div class="file-item">📄 {Path(path).name}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty-files">No file uploaded yet</div>', unsafe_allow_html=True)
    st.markdown('<div class="divider-label"><span>OR</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">2. Tell Editra what you want to do</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Use one draft box for your complete request. It controls retrieval and document generation.</div>', unsafe_allow_html=True)
    query = st.text_area("Task draft", placeholder="Describe your task... e.g. Summarize the document, extract key insights, explain the important numbers, and create a concise report.", height=160, max_chars=2000, label_visibility="collapsed")
    output_type = st.selectbox("Output format", ["Auto", "PDF", "PPT", "DOCX", "TXT"], format_func=lambda x: "Auto · Best format for your request" if x == "Auto" else x)
    if st.button("✦  Generate Document  →", type="primary", use_container_width=True):
        paths = getattr(st.session_state, "upload_paths", [])
        mapped = "Auto" if output_type == "Auto" else {"PDF":"pdf","PPT":"pptx","DOCX":"docx","TXT":"txt"}[output_type]
        if not paths: st.error("Please upload a source document first.")
        elif not query.strip(): st.error("Please describe what you want Editra to create.")
        else:
            with st.spinner("Ingesting → embedding → retrieving → analyzing → generating → validating…"):
                result = st.session_state.query_pipeline.run(query, query, paths, mapped)
            if result.get("artifact"):
                st.session_state.current_artifact = result["artifact"]
                st.session_state.messages += [{"role":"user","content":query},{"role":"assistant","content":result["message"],"artifact":result["artifact"],"sources":result.get("sources",[])}]
                st.rerun()
            else: st.error(result.get("message", "Generation failed."))
    st.markdown('</div>', unsafe_allow_html=True)

last_assistant_index = max((i for i,m in enumerate(st.session_state.messages) if m.get("role")=="assistant"), default=-1)
for i,m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if i == last_assistant_index and m.get("artifact"):
            a=m["artifact"]
            st.markdown(f"**Output:** {a['filename']} · version {a['version']}")
            st.download_button("⬇ Download editable file", data=Path(a["path"]).read_bytes(), file_name=a["filename"], mime=a["mime"], key=f"download_{a['id']}", use_container_width=True)
            if a["preview_type"] == "images":
                for img in a["preview"]: st.image(img, use_container_width=True)
            else: st.info(a["preview"])
            if m.get("sources"):
                with st.expander("Sources & traceability"):
                    for source in m["sources"]: st.write(source)

if st.session_state.current_artifact:
    prompt = st.chat_input("Ask Editra to modify the current generated artifact…")
    if prompt:
        st.session_state.messages.append({"role":"user","content":prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Applying and validating the requested edit…"):
                result=st.session_state.orch.run(prompt, getattr(st.session_state,"upload_paths",[]), st.session_state.current_artifact, st.session_state.messages)
            if result.get("artifact"):
                st.session_state.current_artifact=result["artifact"]
                a=result["artifact"]
                st.markdown(f"**Output:** {a['filename']} · version {a['version']}")
                st.download_button("⬇ Download editable file", data=Path(a["path"]).read_bytes(), file_name=a["filename"], mime=a["mime"], key=f"download_live_{a['id']}", use_container_width=True)
            else: st.error(result.get("message","Edit failed."))
            st.session_state.messages.append({"role":"assistant","content":result.get("message","Output generated successfully.") if not result.get("artifact") else "Output generated successfully.","artifact":result.get("artifact"),"sources":result.get("sources",[])})
