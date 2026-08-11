import io
import logging

import docx
import pymupdf
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def _clean_extracted_text(text: str) -> str:
    """
    Normalize only whitespace introduced by PDF extraction.

    Important: do not collapse all newlines. The chunker uses line
    boundaries to detect Week/Day/Chapter/etc. hierarchy and to
    preserve lists.
    """
    text = str(text or "").replace("\x00", "")

    lines = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.strip():
            lines.append(line.strip())
        elif lines and lines[-1] != "":
            lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines).strip()


def parse_pdf(file_bytes: bytes, filename: str) -> list[dict]:
    """
    Extract every text-bearing PDF page in reading order.

    Page numbers are preserved exactly so citations continue to point
    to the real PDF page. Empty pages are skipped, but page numbering
    is never renumbered.
    """
    try:
        with pymupdf.open(
            stream=file_bytes,
            filetype="pdf",
        ) as doc:

            pages = []

            for page_num, page in enumerate(doc):
                text = page.get_text(
                    "text",
                    sort=True,
                )

                text = _clean_extracted_text(
                    text
                )

                if not text:
                    logger.warning(
                        "No extractable text on page %s of %s.",
                        page_num + 1,
                        filename,
                    )
                    continue

                pages.append({
                    "content": text,
                    "metadata": {
                        "source": filename,
                        "page": page_num + 1,
                    },
                })

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid or corrupted PDF file: "
                f"{exc}"
            ),
        )

    if not pages:
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not extract text from document. "
                "The PDF may be scanned/image-only or "
                "password-protected."
            ),
        )

    logger.info(
        "Extracted %s text pages from %s.",
        len(pages),
        filename,
    )

    return pages


def parse_docx(
    file_bytes: bytes,
    filename: str,
) -> list[dict]:
    """
    Extract DOCX paragraphs while preserving paragraph boundaries.
    """
    try:
        doc = docx.Document(
            io.BytesIO(file_bytes)
        )

        paragraphs = [
            para.text.strip()
            for para in doc.paragraphs
            if para.text and para.text.strip()
        ]

        full_text = "\n\n".join(
            paragraphs
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid or corrupted DOCX file: "
                f"{exc}"
            ),
        )

    full_text = _clean_extracted_text(
        full_text
    )

    if not full_text:
        raise HTTPException(
            status_code=400,
            detail=(
                "The DOCX file contains no "
                "extractable text."
            ),
        )

    return [{
        "content": full_text,
        "metadata": {
            "source": filename,
            "page": 1,
        },
    }]
