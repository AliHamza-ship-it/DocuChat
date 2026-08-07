import fitz  # PyMuPDF
import docx
import io
from fastapi import HTTPException

def parse_pdf(file_bytes: bytes, filename: str) -> list[dict]:
    """Extracts text and page numbers from PDF files preserving reading order."""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid or corrupted PDF file: {str(e)}")

    pages = []
    for page_num, page in enumerate(doc):
        text = page.get_text("text", sort=True).strip()
        if text:
            pages.append({
                "content": text,
                "metadata": {"source": filename, "page": page_num + 1}
            })

    if not pages:
        raise HTTPException(
            status_code=400, 
            detail="Could not extract text from document. The PDF may be scanned/image-only or password-protected."
        )
    return pages

def parse_docx(file_bytes: bytes, filename: str) -> list[dict]:
    """Extracts text from DOCX files preserving paragraph headers."""
    try:
        doc = docx.Document(io.BytesIO(file_bytes))
        full_text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid or corrupted DOCX file: {str(e)}")

    if not full_text.strip():
        raise HTTPException(status_code=400, detail="The DOCX file contains no extractable text.")

    return [{
        "content": full_text,
        "metadata": {"source": filename, "page": 1}
    }]