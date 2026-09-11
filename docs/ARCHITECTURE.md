# Editra AI Architecture

## Core flow

Upload -> Analyze -> Supervisor -> Research/RAG -> Generate -> Validate -> Preview -> Download -> Edit -> New Version

## Agent responsibilities

### Supervisor
Classifies create/edit/convert requests and chooses DOCX/PPTX.

### Document Agent
Extracts paragraphs and tables from DOCX and text from PDF/image inputs.

### PPT Agent
Extracts slide text and basic geometry from PPTX.

### Research Agent
Uses Tavily when configured.

### RAG Agent
Queries Pinecone when configured.

### Generation Agents
Create native editable DOCX/PPTX files.

### Validation Agent
Reopens generated files to catch corrupt artifacts.

### Editing Agent
Classifies common editing operations. It can be extended into a richer operation DSL.

## Production upgrades

- Replace simple in-memory version tracking with SQLite/PostgreSQL.
- Add OCR/vision extraction for images and scanned PDFs.
- Add template style cloning at the run/shape/theme level.
- Add true artifact-diff editing.
- Add source-to-paragraph/slide traceability.
- Add authentication and secure file storage.
- Add background jobs for large documents.
