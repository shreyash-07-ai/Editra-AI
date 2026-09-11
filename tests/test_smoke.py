from pathlib import Path
from docx import Document
from pptx import Presentation
from tempfile import TemporaryDirectory

def test_docx_can_be_created():
    with TemporaryDirectory() as d:
        p = Path(d)/"a.docx"
        Document().save(p)
        assert p.exists()

def test_pptx_can_be_created():
    with TemporaryDirectory() as d:
        p = Path(d)/"a.pptx"
        Presentation().save(p)
        assert p.exists()
