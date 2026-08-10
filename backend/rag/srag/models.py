from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class EvidenceChunk:
    chunk_id: str
    document_id: str
    content: str
    metadata: Dict[str, Any] = field(
        default_factory=dict
    )
    similarity: float = 0.0


@dataclass
class SRAGResult:
    answer: str
    sources: List[Dict[str, Any]]
    retrieval_query: str
    retrieval_attempts: int
    support_revisions: int
    rewrite_attempts: int
    status: str
    refusal: bool