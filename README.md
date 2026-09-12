# Editra AI

Editra AI is a Streamlit-based multi-agent POC for generating and conversationally editing editable DOCX, PPTX and XLSX artifacts, with PDF/CSV export and iterative version control (undo, restore-original, format conversion).

## Workflow

1. Upload DOCX, PDF, PPTX, PPT, XLSX, CSV or image files.
2. Give Editra a natural-language prompt.
3. The supervisor routes the task.
4. Documents/PPTs/spreadsheets are analyzed.
5. Optional web research and Pinecone RAG provide additional context.
6. An editable DOCX, PPTX or XLSX is generated.
7. The artifact is validated.
8. A visual preview is shown when LibreOffice is installed.
9. Download the original editable artifact, or export it to PDF/CSV.
10. Continue chatting to generate the next version — including "undo the last change" or "go back to the original".

## Architecture

- Supervisor / Orchestrator Agent
- Document Analysis Agent
- PPT Analysis Agent
- Web Research Agent
- RAG Agent
- DOCX Generator
- PPTX Generator
- XLSX Generator
- Validation Agent
- Conversational Editing Agent
- Artifact Store / Versioning (with undo and original-file recall)
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

## Iterative editing

Every follow-up prompt edits the current working document — never the original upload — unless you explicitly ask to:

- **Undo the last change** — reverts to the previous version (also available as a sidebar button).
- **Go back to the original** — restores the file you first uploaded (also available as a sidebar button). CSV originals are re-normalized into an editable XLSX so editing can continue.
- **Convert / export to a different format** — e.g. "give me a PDF version", "convert this into a PowerPoint", "export the current sheet as CSV". PDF and CSV exports are flattened, read-only snapshots of the current editable version; the next edit request automatically resolves back to the underlying editable DOCX/PPTX/XLSX.

## Visual previews

Install LibreOffice and ensure `libreoffice` (or `soffice`) is available on PATH. Editra converts generated DOCX/PPTX to PDF for both previews and explicit PDF export; the downloadable artifact remains the original editable file unless you ask for a PDF/CSV export.

## Web research

Set `TAVILY_API_KEY` to enable current web research.

## Enterprise RAG

Set `PINECONE_API_KEY` and `PINECONE_INDEX` to enable Pinecone retrieval. You still need to ingest your enterprise documents into the index.

## Important POC note

The code deliberately keeps the artifact generation layer modular. For production-grade template fidelity, extend the DOCX/PPTX/XLSX generators to clone and edit the uploaded template's existing paragraphs, runs, shapes, layouts, tables, charts, cell styles and theme rather than rebuilding from scratch. Several DOCX edit heuristics (e.g. "add an executive summary", "add a competitive analysis section") are deterministic pattern matches tuned to a specific demo proposal document; free-form edit requests fall back to an LLM-generated edit plan that requires `GEMINI_API_KEY`.

## Streamlit deployment

For Streamlit Community Cloud:

1. Push the project to GitHub.
2. Choose `frontend/app.py` as the main file.
3. Add the same secrets from `.env` to Streamlit Secrets.
4. Deploy.

Do not commit `.env` or API keys.

