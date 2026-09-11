from pathlib import Path
import fitz

def preview_pdf(path, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(path)
    images = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=fitz.Matrix(1.3,1.3), alpha=False)
        p = out_dir / f"page_{i+1}.png"
        pix.save(str(p))
        images.append(str(p))
    return images

def preview_pptx(path, out_dir):
    # Native PPTX rendering depends on LibreOffice being installed.
    # This function attempts conversion to PDF, then renders pages.
    import subprocess
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = out_dir / "pdf"
    pdf_dir.mkdir(exist_ok=True)
    try:
        subprocess.run(
            ["libreoffice","--headless","--convert-to","pdf","--outdir",str(pdf_dir),str(path)],
            check=True, capture_output=True
        )
        pdf = pdf_dir / (Path(path).stem + ".pdf")
        if pdf.exists():
            return preview_pdf(pdf, out_dir)
    except Exception:
        pass
    return []

def preview_docx(path, out_dir):
    import subprocess
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = out_dir / "pdf"
    pdf_dir.mkdir(exist_ok=True)
    try:
        subprocess.run(
            ["libreoffice","--headless","--convert-to","pdf","--outdir",str(pdf_dir),str(path)],
            check=True, capture_output=True
        )
        pdf = pdf_dir / (Path(path).stem + ".pdf")
        if pdf.exists():
            return preview_pdf(pdf, out_dir)
    except Exception:
        pass
    return []

def preview(path, artifact_type, out_dir):
    if artifact_type == "pptx": return preview_pptx(path, out_dir)
    if artifact_type == "docx": return preview_docx(path, out_dir)
    return []
