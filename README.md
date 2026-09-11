# Editra AI

Editra AI is a Streamlit-based multi-agent POC for generating and conversationally editing editable DOCX and PPTX artifacts.

## Workflow

1. Upload DOCX, PDF, PPTX or image files.
2. Give Editra a natural-language prompt.
3. The supervisor routes the task.
4. Documents/PPTs are analyzed.
5. Optional web research and Pinecone RAG provide additional context.
6. An editable DOCX or PPTX is generated.
7. The artifact is validated.
8. A visual preview is shown when LibreOffice is installed.
9. Download the original editable artifact.
10. Continue chatting to generate the next version.

## Architecture

- Supervisor / Orchestrator Agent
- Document Analysis Agent
- PPT Analysis Agent
- Web Research Agent
- RAG Agent
- DOCX Generator
- PPTX Generator
- Validation Agent
- Conversational Editing Agent
- Artifact Store / Versioning
- Streamlit UI

## Setup — Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Put your API keys in `.env`.

Run:

```powershell
streamlit run frontend/app.py
```

## Visual previews

Install LibreOffice and ensure `libreoffice` is available on PATH. Editra converts generated DOCX/PPTX to PDF only for preview; the downloadable artifact remains the original editable DOCX/PPTX.

## Web research

Set `TAVILY_API_KEY` to enable current web research.

## Enterprise RAG

Set `PINECONE_API_KEY` and `PINECONE_INDEX` to enable Pinecone retrieval. You still need to ingest your enterprise documents into the index.

## Important POC note

The code deliberately keeps the artifact generation layer modular. For production-grade template fidelity, extend the DOCX/PPTX generators to clone and edit the uploaded template's existing paragraphs, runs, shapes, layouts, tables, charts and theme rather than rebuilding from scratch.

## Streamlit deployment

For Streamlit Community Cloud:

1. Push the project to GitHub.
2. Choose `frontend/app.py` as the main file.
3. Add the same secrets from `.env` to Streamlit Secrets.
4. Deploy.

Do not commit `.env` or API keys.
