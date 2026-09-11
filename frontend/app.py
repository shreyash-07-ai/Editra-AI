import streamlit as st
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.orchestrator import EditraOrchestrator
from backend.storage import ArtifactStore

st.set_page_config(page_title="Editra AI", page_icon="✦", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; max-width: 1200px;}
[data-testid="stSidebar"] {min-width: 260px;}
.chat-title {font-size: 2rem; font-weight: 700; margin-bottom: .2rem;}
.chat-subtitle {color:#777; margin-bottom:1.2rem;}
.artifact-card {padding:1rem; border:1px solid #ddd; border-radius:12px; margin:.5rem 0;}
.small {font-size:.85rem;color:#777;}
</style>
""", unsafe_allow_html=True)

if "store" not in st.session_state:
    st.session_state.store = ArtifactStore()
if "orch" not in st.session_state:
    st.session_state.orch = EditraOrchestrator(st.session_state.store)
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_artifact" not in st.session_state:
    st.session_state.current_artifact = None

with st.sidebar:
    st.markdown("## ✦ Editra AI")
    st.caption("Editable document & presentation editor")
    if st.button("＋ New chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.current_artifact = None
        st.rerun()

    st.divider()
    st.markdown("### Upload files")
    uploads = st.file_uploader(
        "DOCX, PDF, PPTX, PPT, PNG, JPG, JPEG",
        type=["docx","pdf","pptx","ppt","png","jpg","jpeg"],
        accept_multiple_files=True
    )

    if uploads:
        saved = []
        for up in uploads:
            p = st.session_state.store.save_upload(up.name, up.getvalue())
            saved.append(str(p))
        st.session_state.upload_paths = saved
        st.success(f"{len(saved)} file(s) ready")

    st.divider()
    st.markdown("### Capabilities")
    st.caption("• DOCX / PPTX generation")
    st.caption("• Conversational editing")
    st.caption("• PDF / image extraction")
    st.caption("• Optional web research")
    st.caption("• Optional Pinecone RAG")
    st.caption("• Version history")

st.markdown('<div class="chat-title">Editra AI</div>', unsafe_allow_html=True)
st.markdown('<div class="chat-subtitle">Upload an artifact, describe the change, preview the result, and keep editing until you are satisfied.</div>', unsafe_allow_html=True)

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("artifact"):
            a = m["artifact"]
            st.markdown(f"**{a['filename']}** — version {a['version']}")
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "⬇ Download editable file",
                    data=Path(a["path"]).read_bytes(),
                    file_name=a["filename"],
                    mime=a["mime"],
                    key=f"download_{a['id']}"
                )
            with col2:
                if a["preview_type"] == "images":
                    st.caption("Preview")
                    for img in a["preview"]:
                        st.image(img, use_container_width=True)
                else:
                    st.caption(a["preview"])

prompt = st.chat_input("Ask Editra to create or modify your document…")

if prompt:
    st.session_state.messages.append({"role":"user","content":prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Editra is analyzing, editing, generating and validating…"):
            upload_paths = getattr(st.session_state, "upload_paths", [])
            result = st.session_state.orch.run(
                prompt=prompt,
                upload_paths=upload_paths,
                current_artifact=st.session_state.current_artifact,
                conversation=st.session_state.messages,
            )

        st.markdown(result["message"])
        if result.get("artifact"):
            st.session_state.current_artifact = result["artifact"]
            a = result["artifact"]
            st.markdown(f"**{a['filename']}** — version {a['version']}")
            st.download_button(
                "⬇ Download editable file",
                data=Path(a["path"]).read_bytes(),
                file_name=a["filename"],
                mime=a["mime"],
                key=f"download_live_{a['id']}"
            )
            if a["preview_type"] == "images":
                for img in a["preview"]:
                    st.image(img, use_container_width=True)
            else:
                st.info(a["preview"])

            if result.get("sources"):
                with st.expander("Sources & traceability"):
                    for s in result["sources"]:
                        st.write(s)

        st.session_state.messages.append({
            "role":"assistant",
            "content":result["message"],
            "artifact":result.get("artifact")
        })
