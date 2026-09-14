import streamlit as st
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.orchestrator import EditraOrchestrator
from backend.query_pipeline import QueryDrivenPipeline
from backend.storage import ArtifactStore

st.set_page_config(page_title="Editra AI", page_icon="✦", layout="wide")

# Keep the interface intentionally simple: white surfaces, soft gray background,
# and one purple accent for the primary actions.
css_path = Path(__file__).with_name("ui_theme.css")
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

if "store" not in st.session_state:
    st.session_state.store = ArtifactStore()
if "orch" not in st.session_state:
    st.session_state.orch = EditraOrchestrator(st.session_state.store)
if "query_pipeline" not in st.session_state:
    st.session_state.query_pipeline = QueryDrivenPipeline(st.session_state.store)
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_artifact" not in st.session_state:
    st.session_state.current_artifact = None

with st.sidebar:
    st.markdown('<div class="editra-brand">✦ Editra <span>AI</span></div>', unsafe_allow_html=True)
    st.caption("Query-driven editable document editor")

    if st.button("＋ New chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.current_artifact = None
        st.session_state.pop("upload_paths", None)
        st.rerun()

    st.divider()
    st.markdown("**Source document**")
    st.caption("PDF, DOCX, PPTX, PPT, XLSX, CSV, PNG, JPG, JPEG · up to 200MB/file")
    uploads = st.file_uploader(
        "Upload source files",
        type=["docx", "pdf", "pptx", "ppt", "xlsx", "csv", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if uploads:
        st.session_state.upload_paths = [
            str(st.session_state.store.save_upload(up.name, up.getvalue())) for up in uploads
        ]
        st.success(f"{len(uploads)} file(s) ready")

    if st.session_state.current_artifact:
        st.divider()
        st.markdown(f"**Current version:** v{st.session_state.current_artifact['version']}")
        c1, c2 = st.columns(2)
        with c1:
            undo_clicked = st.button("↩ Undo", use_container_width=True)
        with c2:
            restore_clicked = st.button("⭯ Original", use_container_width=True)
    else:
        undo_clicked = restore_clicked = False

    st.divider()
    st.markdown("**What Editra can do**")
    for item in [
        "Extract and semantically chunk documents",
        "Gemini embeddings + Pinecone RAG",
        "Query-driven analysis",
        "Optional web research",
        "Generate editable PDF / PPT / DOCX / TXT",
        "Conversational editing and versioning",
    ]:
        st.caption(f"• {item}")

st.markdown('<div class="editra-title">Create with your documents</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="editra-subtitle">Upload a source, describe the task, and generate a new editable document.</div>',
    unsafe_allow_html=True,
)

if not st.session_state.current_artifact:
    st.markdown('<div class="editra-card">', unsafe_allow_html=True)
    st.markdown('<div class="editra-step">Step 1 · Upload</div>', unsafe_allow_html=True)
    st.write("Use the upload area in the sidebar to add your source material.")
    if getattr(st.session_state, "upload_paths", []):
        st.success(f"{len(st.session_state.upload_paths)} source file(s) ready for processing.")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="editra-card">', unsafe_allow_html=True)
    st.markdown('<div class="editra-step">Step 2 · Describe</div>', unsafe_allow_html=True)
    query = st.text_area(
        "What would you like Editra to do?",
        placeholder="Example: Analyze the key numerical findings, explain their significance, and create a concise report.",
        height=120,
        label_visibility="visible",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="editra-card">', unsafe_allow_html=True)
    st.markdown('<div class="editra-step">Step 3 · Generate</div>', unsafe_allow_html=True)
    output_type = st.selectbox("Output type", ["Auto", "PDF", "PPT", "DOCX", "TXT"])

    if st.button("✦  Generate NEW document", type="primary", use_container_width=True):
        paths = getattr(st.session_state, "upload_paths", [])
        mapped = "Auto" if output_type == "Auto" else {
            "PDF": "pdf", "PPT": "pptx", "DOCX": "docx", "TXT": "txt"
        }[output_type]

        if not paths:
            st.error("Upload a source document first.")
        elif not query.strip():
            st.error("Describe what you want Editra to create.")
        else:
            with st.spinner("Ingesting → embedding → retrieving → analyzing → generating → validating…"):
                result = st.session_state.query_pipeline.run(query, query, paths, mapped)

            if result.get("artifact"):
                st.session_state.current_artifact = result["artifact"]
                st.session_state.messages += [
                    {"role": "user", "content": query},
                    {
                        "role": "assistant",
                        "content": result["message"],
                        "artifact": result["artifact"],
                        "sources": result.get("sources", []),
                    },
                ]
                st.rerun()
            else:
                st.error(result.get("message", "Generation failed."))
    st.markdown('</div>', unsafe_allow_html=True)

last_assistant_index = max(
    (i for i, m in enumerate(st.session_state.messages) if m.get("role") == "assistant"),
    default=-1,
)

for i, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if i == last_assistant_index and m.get("artifact"):
            a = m["artifact"]
            st.markdown(f"**Output:** {a['filename']} · version {a['version']}")
            st.download_button(
                "⬇ Download editable file",
                data=Path(a["path"]).read_bytes(),
                file_name=a["filename"],
                mime=a["mime"],
                key=f"download_{a['id']}",
                use_container_width=True,
            )
            if a["preview_type"] == "images":
                for img in a["preview"]:
                    st.image(img, use_container_width=True)
            else:
                st.info(a["preview"])
            if m.get("sources"):
                with st.expander("Sources & traceability"):
                    for source in m["sources"]:
                        st.write(source)

if st.session_state.current_artifact:
    prompt = st.chat_input("Ask Editra to modify the current generated artifact…")
    if undo_clicked:
        prompt = "undo the last change"
    elif restore_clicked:
        prompt = "go back to the original"

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Applying and validating the requested edit…"):
                result = st.session_state.orch.run(
                    prompt,
                    getattr(st.session_state, "upload_paths", []),
                    st.session_state.current_artifact,
                    st.session_state.messages,
                )
            if result.get("artifact"):
                st.session_state.current_artifact = result["artifact"]
                a = result["artifact"]
                st.markdown(f"**Output:** {a['filename']} · version {a['version']}")
                st.download_button(
                    "⬇ Download editable file",
                    data=Path(a["path"]).read_bytes(),
                    file_name=a["filename"],
                    mime=a["mime"],
                    key=f"download_live_{a['id']}",
                    use_container_width=True,
                )
                if a["preview_type"] == "images":
                    for img in a["preview"]:
                        st.image(img, use_container_width=True)
                else:
                    st.info(a["preview"])
                if result.get("sources"):
                    with st.expander("Sources & traceability"):
                        for source in result["sources"]:
                            st.write(source)
            else:
                st.error(result.get("message", "Edit failed."))
            st.session_state.messages.append({
                "role": "assistant",
                "content": result.get("message", "Output generated successfully.") if not result.get("artifact") else "Output generated successfully.",
                "artifact": result.get("artifact"),
                "sources": result.get("sources", []),
            })
