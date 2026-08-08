from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


@dataclass
class EvidenceChunk:
    """
    A retrieved document chunk together with metadata required
    for ranking, validation, and citations.
    """

    chunk_id: str
    document_id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    similarity: float = 0.0
    relevance_score: float = 0.0

    @property
    def source(self) -> str:
        return str(
            self.metadata.get(
                "source",
                "Unknown Document"
            )
        )

    @property
    def page(self) -> Any:
        return self.metadata.get("page", 1)

    def to_context(self, index: int) -> str:
        breadcrumbs = self.metadata.get(
            "breadcrumbs",
            ""
        )

        breadcrumb_line = (
            f"\nBreadcrumbs: {breadcrumbs}"
            if breadcrumbs
            else ""
        )

        return (
            f"[EVIDENCE {index}]\n"
            f"Document: {self.source}\n"
            f"Page: {self.page}\n"
            f"Document ID: {self.document_id}\n"
            f"Chunk ID: {self.chunk_id}"
            f"{breadcrumb_line}\n"
            f"Content:\n"
            f"{self.content.strip()}"
        )


@dataclass
class SRAGResult:
    """
    Final result returned by the Self-RAG engine.
    """

    answer: str

    sources: List[Dict[str, Any]]

    retrieval_query: str

    retrieval_attempts: int = 1

    support_revisions: int = 0

    rewrite_attempts: int = 0

    status: str = "success"

    refusal: bool = False

    debug: Optional[Dict[str, Any]] = None


SupportStatus = Literal[
    "fully_supported",
    "partially_supported",
    "no_support"
]

UsefulnessStatus = Literal[
    "useful",
    "not_useful"
]