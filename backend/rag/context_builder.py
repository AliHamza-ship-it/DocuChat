from typing import List

from backend.rag.models import EvidenceChunk


def build_context(
    chunks: List[EvidenceChunk]
) -> str:

    if not chunks:
        return "No validated evidence is available."

    return (
        "\n\n"
        "========================================"
        "\n\n"
    ).join(
        chunk.to_context(index + 1)
        for index, chunk in enumerate(chunks)
    )


def build_sources(
    chunks: List[EvidenceChunk]
) -> list[dict]:

    return [
        {
            "document_id": chunk.document_id,
            "content": chunk.content,
            "metadata": chunk.metadata,
            "similarity": float(
                chunk.similarity
            ),
        }
        for chunk in chunks
    ]