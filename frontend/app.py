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
        st.session_state.pop("upload_paths", None)
        st.rerun()

    st.divider()
    st.markdown("### Upload files")
    uploads = st.file_uploader(
        "DOCX, PDF, PPTX, PPT, XLSX, CSV, PNG, JPG, JPEG",
        type=["docx", "pdf", "pptx", "ppt", "xlsx", "csv", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )

    if uploads:
        saved = []
        for up in uploads:
            p = st.session_state.store.save_upload(up.name, up.getvalue())
            saved.append(str(p))
        st.session_state.upload_paths = saved
        st.success(f"{len(saved)} file(s) ready")

    if st.session_state.current_artifact:
        st.divider()
        st.markdown(f"### Current version: v{st.session_state.current_artifact['version']}")
        col_a, col_b = st.columns(2)
        with col_a:
            undo_clicked = st.button("↩ Undo last change", use_container_width=True)
        with col_b:
            restore_clicked = st.button("⭯ Restore original", use_container_width=True)
    else:
        undo_clicked = restore_clicked = False

    st.divider()
    st.markdown("### Capabilities")
    st.caption("• DOCX / PPTX / XLSX generation")
    st.caption("• Conversational editing")
    st.caption("• PDF / image / spreadsheet extraction")
    st.caption("• PDF export & format conversion")
    st.caption("• Undo & restore-original")
    st.caption("• Optional web research")
    st.caption("• Optional Pinecone RAG")
    st.caption("• Version history")

st.markdown('<div class="chat-title">Editra AI</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="chat-subtitle">Upload an artifact, describe the change, preview the result, and keep editing until you are satisfied.</div>',
    unsafe_allow_html=True,
)

# Show the conversation text, but render an artifact only for the latest
# assistant response. This prevents every previous document version from
# appearing again after Streamlit reruns. The user always sees one current
# output artifact: the document generated from the latest prompt.
last_assistant_index = max(
    (i for i, m in enumerate(st.session_state.messages) if m.get("role") == "assistant"),
    default=-1,
)

for i, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

        # Historical versions remain available through the backend's version
        # chain, but are not rendered as duplicate output cards in the chat.
        if i == last_assistant_index and m.get("artifact"):
            a = m["artifact"]
            st.markdown(f"**Output:** {a['filename']} — version {a['version']}")
            st.download_button(
                "⬇ Download editable file",
                data=Path(a["path"]).read_bytes(),
                file_name=a["filename"],
                mime=a["mime"],
                key=f"download_{a['id']}",
                use_container_width=True,
            )

            if a["preview_type"] == "images":
                st.caption("Preview of the generated output")
                for img in a["preview"]:
                    st.image(img, use_container_width=True)
            else:
                st.info(a["preview"])

            if m.get("sources"):
                with st.expander("Sources & traceability"):
                    for source in m["sources"]:
                        st.write(source)

prompt = st.chat_input("Ask Editra to create or modify your document…")
if undo_clicked:
    prompt = "undo the last change"
elif restore_clicked:
    prompt = "go back to the original"

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
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

        # For every prompt, the response is centered on the newly generated
        # artifact. Do not display the uploaded source as an additional output.
        if result.get("artifact"):
            st.session_state.current_artifact = result["artifact"]
            a = result["artifact"]
            st.markdown(f"**Output:** {a['filename']} — version {a['version']}")
            st.download_button(
                "⬇ Download editable file",
                data=Path(a["path"]).read_bytes(),
                file_name=a["filename"],
                mime=a["mime"],
                key=f"download_live_{a['id']}",
                use_container_width=True,
            )
            if a["preview_type"] == "images":
                st.caption("Preview of the generated output")
                for img in a["preview"]:
                    st.image(img, use_container_width=True)
            else:
                st.info(a["preview"])

            if result.get("sources"):
                with st.expander("Sources & traceability"):
                    for source in result["sources"]:
                        st.write(source)
        else:
            st.error(result["message"])

        # Keep only the response message and the latest artifact reference.
        # Older artifact cards are intentionally not rendered on subsequent
        # Streamlit reruns.
        st.session_state.messages.append({
            "role": "assistant",
            "content": result["message"] if not result.get("artifact") else "Output generated successfully.",
            "artifact": result.get("artifact"),
            "sources": result.get("sources", []),
        })
