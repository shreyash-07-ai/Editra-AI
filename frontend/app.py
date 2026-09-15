import streamlit as st
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.orchestrator import EditraOrchestrator
from backend.query_pipeline import QueryDrivenPipeline
from backend.storage import ArtifactStore

st.set_page_config(page_title="Editra AI", page_icon="✦", layout="wide", initial_sidebar_state="collapsed")
css = Path(__file__).with_name("ui_theme_v2.css")
if css.exists():
    st.markdown(f"<style>{css.read_text()}</style>", unsafe_allow_html=True)

if "store" not in st.session_state: st.session_state.store = ArtifactStore()
if "orch" not in st.session_state: st.session_state.orch = EditraOrchestrator(st.session_state.store)
if "query_pipeline" not in st.session_state: st.session_state.query_pipeline = QueryDrivenPipeline(st.session_state.store)
if "messages" not in st.session_state: st.session_state.messages = []
if "current_artifact" not in st.session_state: st.session_state.current_artifact = None

# Main header replaces the permanent sidebar.
head_left, head_right = st.columns([4, 1])
with head_left:
    st.markdown('<div class="editra-brand">✦ Editra <span>AI</span></div><div class="brand-sub">Your AI document editor</div>', unsafe_allow_html=True)
with head_right:
    st.markdown('<div class="new-chat-wrap">', unsafe_allow_html=True)
    if st.button("＋  New chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.current_artifact = None
        st.session_state.pop("upload_paths", None)
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="editra-badge">✦ AI-Powered Document Editing</div>', unsafe_allow_html=True)
st.markdown('<div class="editra-title">Create with your <span>documents</span></div>', unsafe_allow_html=True)
st.markdown('<div class="editra-subtitle">Upload a document and tell Editra what you need. Get an editable file in seconds.</div>', unsafe_allow_html=True)

if not st.session_state.current_artifact:
    st.markdown('<div class="workspace-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">1. Upload your document</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Add the source material Editra should use as evidence.</div>', unsafe_allow_html=True)
    uploads = st.file_uploader("Upload source document", type=["docx","pdf","pptx","ppt","xlsx","csv","png","jpg","jpeg"], accept_multiple_files=True, key="main_uploader")
    if uploads:
        st.session_state.upload_paths = [str(st.session_state.store.save_upload(x.name, x.getvalue())) for x in uploads]
        st.success(f"{len(uploads)} source file(s) ready")
    paths = getattr(st.session_state, "upload_paths", [])
    if paths:
        st.markdown('<div class="uploaded-list">', unsafe_allow_html=True)
        for path in paths:
            st.markdown(f'<div class="file-item">📄 <strong>{Path(path).name}</strong><span>Ready</span></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title draft-title">2. Your task</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-note">Write your complete request in one draft. Editra uses it for retrieval and document generation.</div>', unsafe_allow_html=True)
    query = st.text_area("Task draft", placeholder="Describe what you want Editra to do...\n\nExample: Summarize this document, extract the important numerical findings, explain their significance, and create a concise report.", height=180, max_chars=2000, label_visibility="collapsed")
    format_col, action_col = st.columns([1, 2.2], gap="medium")
    with format_col:
        output_type = st.selectbox("Output format", ["Auto","PDF","PPT","DOCX","TXT"], format_func=lambda x: "Auto · Best format" if x == "Auto" else x)
    with action_col:
        st.markdown('<div class="generate-label">Ready to create?</div>', unsafe_allow_html=True)
        generate = st.button("✦  Generate Document  →", type="primary", use_container_width=True)
    if generate:
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
            else: st.error(result.get("message","Generation failed."))
    st.markdown('</div>', unsafe_allow_html=True)

if st.session_state.current_artifact:
    a = st.session_state.current_artifact
    st.markdown(f'<div class="result-header"><div class="result-kicker">DOCUMENT READY</div><div class="result-title">Your editable document is ready</div><div class="result-meta">{a["filename"]} · Version {a["version"]}</div></div>', unsafe_allow_html=True)
    latest = next((m for m in reversed(st.session_state.messages) if m.get("artifact")), None)
    if latest:
        st.markdown('<div class="result-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="result-message">{latest.get("content", "Document generated successfully.")}</div>', unsafe_allow_html=True)
        st.download_button("⬇  Download editable document", data=Path(a["path"]).read_bytes(), file_name=a["filename"], mime=a["mime"], key=f"download_{a['id']}", use_container_width=True)
        if a["preview_type"] == "images":
            for img in a["preview"]: st.image(img, use_container_width=True)
        else: st.info(a["preview"])
        if latest.get("sources"):
            with st.expander("Sources & traceability"):
                for source in latest["sources"]: st.write(source)
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div class="chat-section-title">Continue editing</div>', unsafe_allow_html=True)
    st.markdown('<div class="chat-section-note">Ask Editra to change the generated document. Each request creates a new version.</div>', unsafe_allow_html=True)
    edit_col1, edit_col2 = st.columns(2)
    with edit_col1: undo = st.button("↩ Undo last change", use_container_width=True)
    with edit_col2: restore = st.button("⭯ Restore original", use_container_width=True)
    prompt = st.chat_input("Describe your next edit… e.g. Make the summary shorter and add a table of key values")
    if undo: prompt = "undo the last change"
    elif restore: prompt = "go back to the original"
    if prompt:
        st.session_state.messages.append({"role":"user","content":prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Applying and validating your edit…"):
                result = st.session_state.orch.run(prompt, getattr(st.session_state,"upload_paths",[]), st.session_state.current_artifact, st.session_state.messages)
            if result.get("artifact"):
                st.session_state.current_artifact = result["artifact"]
                new_a = result["artifact"]
                st.markdown(f"**Version {new_a['version']} created** · {new_a['filename']}")
                st.download_button("⬇ Download latest version", data=Path(new_a["path"]).read_bytes(), file_name=new_a["filename"], mime=new_a["mime"], key=f"download_live_{new_a['id']}", use_container_width=True)
                if new_a["preview_type"] == "images":
                    for img in new_a["preview"]: st.image(img, use_container_width=True)
                else: st.info(new_a["preview"])
                if result.get("sources"):
                    with st.expander("Sources & traceability"):
                        for source in result["sources"]: st.write(source)
            else: st.error(result.get("message","Edit failed."))
            st.session_state.messages.append({"role":"assistant","content":result.get("message", "Output generated successfully.") if not result.get("artifact") else "Output generated successfully.","artifact":result.get("artifact"),"sources":result.get("sources",[])})
