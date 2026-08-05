import fitz  # PyMuPDF
import docx
import io
from fastapi import UploadFile

def parse_pdf(file_bytes: bytes, filename: str) -> list[dict]:
    """Extracts text and page numbers from PDF files."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    for page_num, page in enumerate(doc):
        text = page.get_text("text").strip()
        if text:
            pages.append({
                "content": text,
                "metadata": {"source": filename, "page": page_num + 1}
            })
    return pages

def parse_docx(file_bytes: bytes, filename: str) -> list[dict]:
    """Extracts text from DOCX files. Pages aren't strictly defined in docx."""
    doc = docx.Document(io.BytesIO(file_bytes))
    full_text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    return [{
        "content": full_text,
        "metadata": {"source": filename, "page": 1}
    }]