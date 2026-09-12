# Editra AI Architecture

## Core flow

Upload -> Analyze -> Supervisor -> Research/RAG -> Generate -> Validate -> Preview -> Download -> Edit -> New Version

Every prompt after the first resolves against the current *editable* working
document (DOCX/PPTX/XLSX), never the original upload — with three explicit
exceptions the orchestrator checks before anything else:

- **Undo** ("undo the last change") — points the working version back at the
  previous entry in the conversation's version history.
- **Restore original** ("go back to the original") — copies the very first
  uploaded file back in as a new version (CSV originals are re-normalized to
  XLSX so editing can continue).
- **Format export/conversion** ("give me a PDF", "convert this to PowerPoint",
  "export as CSV") — PDF and CSV are flattened, read-only snapshots that carry
  an `editable_source` pointer back to the real working document, so the next
  structural edit request still lands on the right file instead of the export.

## Agent responsibilities

### Supervisor
Classifies create/edit/convert requests and chooses DOCX/PPTX/XLSX.

### Document Agent
Extracts paragraphs and tables from DOCX, text from PDF/image inputs, and rows/headers from XLSX/CSV.

### PPT Agent
Extracts slide text and basic geometry from PPTX.

### Research Agent
Uses Tavily when configured.

### RAG Agent
Queries Pinecone when configured.

### Generation Agents
Create native editable DOCX/PPTX/XLSX files. PDF export is a separate,
non-editable conversion step (LibreOffice headless) applied to the current
working document, not a generator in its own right.

### Validation Agent
Reopens generated files (DOCX/PPTX/XLSX/CSV/PDF) to catch corrupt artifacts.

### Editing Agent
Classifies common editing operations per artifact type (DOCX/PPTX/XLSX). It can be extended into a richer operation DSL.

## Error handling

Every generation and analysis call in the orchestrator is wrapped so a failed
edit, an unreadable/corrupted upload, or a missing LibreOffice binary returns
a plain-language message instead of crashing the request — the current
working version is never replaced with a broken or partial file.

## Production upgrades

- Replace simple in-memory version tracking with SQLite/PostgreSQL.
- Add OCR/vision extraction for images and scanned PDFs.
- Add template style cloning at the run/shape/cell/theme level.
- Add true artifact-diff editing.
- Add source-to-paragraph/slide/cell traceability.
- Add authentication and secure file storage.
- Add background jobs for large documents.
- Add audio/video transcription as an input modality.
- Replace the hardcoded DOCX edit heuristics with a fully general, LLM-driven plan for every request (currently a few common edits are deterministic pattern matches tuned to a demo proposal document; everything else requires `GEMINI_API_KEY`).
