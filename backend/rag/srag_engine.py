import logging
import re
from typing import Any, Dict, List

from backend.core.config import settings
from backend.embeddings.vectorizer import embedding_service
from backend.rag.context_builder import (
    build_context,
    build_sources
)
from backend.rag.models import (
    EvidenceChunk,
    SRAGResult
)
from backend.rag.query_rewriter import (
    QueryRewriter
)
from backend.rag.validators import (
    SRAGValidators
)
from backend.storage.vector_store import (
    vector_store
)


logger = logging.getLogger(__name__)


REFUSAL_TEXT = (
    "I cannot answer this question based on "
    "the provided documents."
)


class SRAGEngine:
    """
    Self-RAG orchestration engine.

    Flow:

        User Question
             ↓
        Retrieval Decision
             ↓
        Query Rewrite
             ↓
        Retrieve
             ↓
        Relevance
             ↓
        Generate
             ↓
        IsSUP
             ↓
        Revise if necessary
             ↓
        IsUSE
             ↓
        Final Answer

    The engine fails closed whenever evidence is insufficient.
    """

    def __init__(self, generator):

        self.generator = generator

        self.query_rewriter = QueryRewriter(
            generator.client,
            generator.model_name
        )

        self.validators = SRAGValidators(
            generator.client,
            generator.model_name
        )

        self.max_retrieval_attempts = (
            settings.SRAG_MAX_RETRIEVAL_ATTEMPTS
        )

        self.max_support_revisions = (
            settings.SRAG_MAX_SUPPORT_REVISIONS
        )

        self.max_rewrite_attempts = (
            settings.SRAG_MAX_REWRITE_ATTEMPTS
        )

        self.initial_retrieval_k = (
            settings.SRAG_RETRIEVAL_CANDIDATES
        )

        self.relevance_min_similarity = (
            settings.SRAG_MIN_SIMILARITY
        )

        self.final_context_k = (
            settings.SRAG_CONTEXT_CHUNKS
        )

    # =========================================================
    # CONVERSATIONAL DECISION
    # =========================================================

    @staticmethod
    def _is_conversational(
        question: str
    ) -> bool:

        """
        Only obvious conversational/meta messages
        bypass document retrieval.

        If uncertain -> retrieve.
        """

        normalized = re.sub(
            r"[^a-z0-9\s]",
            "",
            question.lower()
        ).strip()

        simple_patterns = [

            r"^(hi|hello|hey|salam|assalamualaikum)$",

            r"^(thanks|thank you|thx)$",

            r"^(what can you do|"
            r"what are you able to do|"
            r"how can you help)$",

            r"^(are you there|"
            r"can i ask a question)$",
        ]

        return any(
            re.match(
                pattern,
                normalized
            )
            for pattern in simple_patterns
        )

    def _generate_conversational(
        self,
        question: str
    ) -> str:

        system = """
You are DocuChat, an enterprise document assistant.

Answer this simple conversational/meta message naturally and briefly.

Do not invent facts about the user's documents.

If asked what you can do, say that you can answer questions
based on the user's uploaded documents.
""".strip()

        return self.generator._complete(
            question,
            system_prompt=system,
            max_tokens=250
        )

    # =========================================================
    # CHUNK NORMALIZATION
    # =========================================================

    @staticmethod
    def _normalize_chunks(
        raw_chunks: List[dict]
    ) -> List[EvidenceChunk]:

        result = []

        for idx, item in enumerate(
            raw_chunks or []
        ):

            content = str(
                item.get(
                    "content",
                    ""
                )
            ).strip()

            if not content:
                continue

            result.append(
                EvidenceChunk(

                    chunk_id=str(
                        item.get(
                            "id",
                            f"retrieved-{idx}"
                        )
                    ),

                    document_id=str(
                        item.get(
                            "document_id",
                            ""
                        )
                    ),

                    content=content,

                    metadata=(
                        item.get(
                            "metadata"
                        )
                        or {}
                    ),

                    similarity=float(
                        item.get(
                            "similarity",
                            0.0
                        )
                    ),
                )
            )

        return result

    # =========================================================
    # DEDUPLICATION
    # =========================================================

    @staticmethod
    def _deduplicate(
        chunks: List[EvidenceChunk]
    ) -> List[EvidenceChunk]:

        seen = set()

        output = []

        for chunk in chunks:

            key = (
                chunk.document_id,
                chunk.content.strip()
            )

            if key in seen:
                continue

            seen.add(key)

            output.append(chunk)

        return output

    # =========================================================
    # RETRIEVAL
    # =========================================================

    def _retrieve(
        self,
        query: str,
        user_id: str
    ) -> List[EvidenceChunk]:

        query_embedding = (
            embedding_service.generate_embedding(
                query
            )
        )

        raw = vector_store.search_similar(
            query_embedding=query_embedding,
            user_id=user_id,
            top_k=self.initial_retrieval_k,
            threshold=self.relevance_min_similarity,
            query_text=query
        )

        chunks = self._normalize_chunks(
            raw
        )

        return self._deduplicate(
            chunks
        )

    # =========================================================
    # RELEVANCE
    # =========================================================

    def _select_relevant(
        self,
        question: str,
        chunks: List[EvidenceChunk]
    ) -> List[EvidenceChunk]:

        if not chunks:
            return []

        # Cheap first gate.
        candidates = [
            chunk
            for chunk in chunks
            if chunk.similarity
            >= self.relevance_min_similarity
        ]

        if not candidates:
            return []

        # LLM relevance validation.
        relevant = (
            self.validators.relevance(
                question,
                candidates
            )
        )

        if not relevant:
            return []

        relevant.sort(
            key=lambda x: x.similarity,
            reverse=True
        )

        return relevant[
            :self.final_context_k
        ]

    # =========================================================
    # CITATION INSTRUCTION
    # =========================================================

    @staticmethod
    def _citation_instruction() -> str:

        return (
            "Every factual statement must have an "
            "inline citation immediately after it "
            "in exactly this format: "
            "[Source: <filename>, Page: <page_number>]. "
            "Use only source/page metadata present "
            "in the evidence."
        )

    # =========================================================
    # GENERATION
    # =========================================================

    def _generate(
        self,
        question: str,
        chunks: List[EvidenceChunk]
    ) -> str:

        context = build_context(
            chunks
        )

        system = f"""
You are DocuChat, a strict enterprise document assistant.

Answer the user's question using ONLY the supplied evidence.

Do not use your general knowledge for factual claims.

Do not invent:

- names
- dates
- numbers
- policies
- product details
- technical specifications
- explanations

If the evidence does not support the answer, say exactly:

{REFUSAL_TEXT}

{self._citation_instruction()}

For document questions:

- Answer directly.
- Use clean Markdown.
- Keep the answer concise but complete.
- Do not mention retrieval.
- Do not mention validation.
- Do not mention prompts.
- Do not reveal hidden reasoning.

EVIDENCE:

{context}
""".strip()

        return self.generator._complete(
            question,
            system_prompt=system,
            max_tokens=1800
        )

    # =========================================================
    # ANSWER REVISION
    # =========================================================

    def _revise(
        self,
        question: str,
        answer: str,
        chunks: List[EvidenceChunk],
        unsupported_claims: List[str]
    ) -> str:

        context = build_context(
            chunks
        )

        unsupported = "\n".join(
            f"- {claim}"
            for claim in unsupported_claims[:10]
        )

        if not unsupported:
            unsupported = (
                "- Unsupported claim(s) detected"
            )

        system = f"""
You are a strict answer reviser for an enterprise document assistant.

Rewrite the answer so that EVERY factual statement
is directly supported by the evidence.

Remove unsupported claims rather than guessing.

Do not add facts from outside knowledge.

Keep the answer useful and direct.

{self._citation_instruction()}

If the evidence cannot answer the question, output exactly:

{REFUSAL_TEXT}

Unsupported claims detected:

{unsupported}

EVIDENCE:

{context}
""".strip()

        return self.generator._complete(
            answer,
            system_prompt=system,
            max_tokens=1800
        )

    # =========================================================
    # MAIN SRAG PIPELINE
    # =========================================================

    def answer(
        self,
        question: str,
        user_id: str,
        conversation: List[
            Dict[str, str]
        ] | None = None
    ) -> SRAGResult:

        question = question.strip()

        conversation = (
            conversation
            or []
        )

        # -----------------------------------------------------
        # DECIDE RETRIEVAL
        # -----------------------------------------------------

        if self._is_conversational(
            question
        ):

            try:

                answer = (
                    self
                    ._generate_conversational(
                        question
                    )
                    .strip()
                )

            except Exception:

                answer = (
                    "I can answer questions "
                    "based on your uploaded documents."
                )

            return SRAGResult(

                answer=answer,

                sources=[],

                retrieval_query="",

                retrieval_attempts=0,

                support_revisions=0,

                rewrite_attempts=0,

                status="direct_conversational",

                refusal=False,
            )

# -----------------------------------------------------
# INITIAL RETRIEVAL
# -----------------------------------------------------
#
# Do NOT make query rewriting a dependency for the
# first retrieval.
#
# The user's original question is usually already the
# strongest and safest query.
# -----------------------------------------------------

        retrieval_query = question

        retrieval_attempts = 0

        rewrite_attempts = 0

        support_revisions = 0

        last_chunks = []

        last_relevant = []

        # -----------------------------------------------------
        # RETRIEVAL LOOP
        # -----------------------------------------------------

        while (
            retrieval_attempts
            < self.max_retrieval_attempts
        ):

            retrieval_attempts += 1

            logger.info(
                "SRAG retrieval attempt "
                "%s/%s query=%s",

                retrieval_attempts,

                self.max_retrieval_attempts,

                retrieval_query
            )

            try:

                last_chunks = self._retrieve(
                    retrieval_query,
                    user_id
                )

                last_relevant = (
                    self._select_relevant(
                        question,
                        last_chunks
                    )
                )

            except Exception as exc:

                logger.exception(
                    "SRAG retrieval failed: %s",
                    exc
                )

                last_chunks = []

                last_relevant = []

            # -------------------------------------------------
            # NO RELEVANT EVIDENCE
            # -------------------------------------------------

            if not last_relevant:

                if (
                    rewrite_attempts
                    >= self.max_rewrite_attempts
                ):

                    return SRAGResult(

                        answer=REFUSAL_TEXT,

                        sources=[],

                        retrieval_query=(
                            retrieval_query
                        ),

                        retrieval_attempts=(
                            retrieval_attempts
                        ),

                        support_revisions=(
                            support_revisions
                        ),

                        rewrite_attempts=(
                            rewrite_attempts
                        ),

                        status=(
                            "no_relevant_evidence"
                        ),

                        refusal=True,
                    )

                rewrite_attempts += 1

                retrieval_query = (
                    self.query_rewriter.rewrite(

                        question,

                        conversation=conversation,

                        previous_query=(
                            retrieval_query
                        ),

                        reason=(
                            "retrieved evidence "
                            "was not relevant enough"
                        )
                    )
                )

                continue

            # -------------------------------------------------
            # GENERATE ANSWER
            # -------------------------------------------------

            answer = (
                self
                ._generate(
                    question,
                    last_relevant
                )
                .strip()
            )

            if not answer:
                answer = REFUSAL_TEXT

            # -------------------------------------------------
            # ISSUP
            # -------------------------------------------------

            support = (
                self.validators.support(

                    question,

                    answer,

                    build_context(
                        last_relevant
                    )
                )
            )

            # -------------------------------------------------
            # SUPPORT LOOP
            # -------------------------------------------------

            while (
                support.get("status")
                != "fully_supported"
            ):

                status = support.get(
                    "status"
                )

                # Partially supported:
                # try to repair the answer first.
                if (
                    status
                    == "partially_supported"
                    and
                    support_revisions
                    < self.max_support_revisions
                ):

                    support_revisions += 1

                    answer = (
                        self
                        ._revise(

                            question,

                            answer,

                            last_relevant,

                            support.get(
                                "unsupported_claims",
                                []
                            )
                        )
                        .strip()
                    )

                    support = (
                        self
                        .validators
                        .support(

                            question,

                            answer,

                            build_context(
                                last_relevant
                            )
                        )
                    )

                    continue

                # -------------------------------------------------
                # UNSUPPORTED ANSWER
                # -------------------------------------------------

                if (
                    rewrite_attempts
                    >= self.max_rewrite_attempts
                    or
                    retrieval_attempts
                    >= self.max_retrieval_attempts
                ):

                    return SRAGResult(

                        answer=REFUSAL_TEXT,

                        sources=build_sources(
                            last_relevant
                        ),

                        retrieval_query=(
                            retrieval_query
                        ),

                        retrieval_attempts=(
                            retrieval_attempts
                        ),

                        support_revisions=(
                            support_revisions
                        ),

                        rewrite_attempts=(
                            rewrite_attempts
                        ),

                        status=(
                            "unsupported_after_retries"
                        ),

                        refusal=True,
                    )

                rewrite_attempts += 1

                retrieval_query = (
                    self.query_rewriter.rewrite(

                        question,

                        conversation=conversation,

                        previous_query=(
                            retrieval_query
                        ),

                        reason=(
                            "answer was not fully "
                            "supported by retrieved evidence"
                        )
                    )
                )

                # Start a fresh retrieval cycle.
                break

            else:

                # -------------------------------------------------
                # ISUSE
                # -------------------------------------------------

                usefulness = (
                    self.validators.usefulness(

                        question,

                        answer
                    )
                )

                if (
                    usefulness.get("isuse")
                    == "useful"
                ):

                    if (
                        answer.strip().lower()
                        == REFUSAL_TEXT.lower()
                    ):

                        return SRAGResult(

                            answer=REFUSAL_TEXT,

                            sources=build_sources(
                                last_relevant
                            ),

                            retrieval_query=(
                                retrieval_query
                            ),

                            retrieval_attempts=(
                                retrieval_attempts
                            ),

                            support_revisions=(
                                support_revisions
                            ),

                            rewrite_attempts=(
                                rewrite_attempts
                            ),

                            status="safe_refusal",

                            refusal=True,
                        )

                    return SRAGResult(

                        answer=answer,

                        sources=build_sources(
                            last_relevant
                        ),

                        retrieval_query=(
                            retrieval_query
                        ),

                        retrieval_attempts=(
                            retrieval_attempts
                        ),

                        support_revisions=(
                            support_revisions
                        ),

                        rewrite_attempts=(
                            rewrite_attempts
                        ),

                        status="success",

                        refusal=False,
                    )

                # -------------------------------------------------
                # ANSWER WAS GROUNDED BUT NOT USEFUL
                # -------------------------------------------------

                if (
                    rewrite_attempts
                    >= self.max_rewrite_attempts
                    or
                    retrieval_attempts
                    >= self.max_retrieval_attempts
                ):

                    return SRAGResult(

                        answer=REFUSAL_TEXT,

                        sources=build_sources(
                            last_relevant
                        ),

                        retrieval_query=(
                            retrieval_query
                        ),

                        retrieval_attempts=(
                            retrieval_attempts
                        ),

                        support_revisions=(
                            support_revisions
                        ),

                        rewrite_attempts=(
                            rewrite_attempts
                        ),

                        status=(
                            "not_useful_after_retries"
                        ),

                        refusal=True,
                    )

                rewrite_attempts += 1

                retrieval_query = (
                    self.query_rewriter.rewrite(

                        question,

                        conversation=conversation,

                        previous_query=(
                            retrieval_query
                        ),

                        reason=(
                            "answer was grounded but "
                            "did not sufficiently answer "
                            "the question"
                        )
                    )
                )
                # Outer retrieval loop starts again.

        # -----------------------------------------------------
        # FINAL SAFE FAILURE
        # -----------------------------------------------------

        return SRAGResult(

            answer=REFUSAL_TEXT,

            sources=build_sources(
                last_relevant
            ),

            retrieval_query=retrieval_query,

            retrieval_attempts=(
                retrieval_attempts
            ),

            support_revisions=(
                support_revisions
            ),

            rewrite_attempts=(
                rewrite_attempts
            ),

            status="retry_limit",

            refusal=True,
        )
