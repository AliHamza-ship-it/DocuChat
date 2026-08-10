import logging
import re
from typing import Dict, List
from backend.prompts.system_prompts import (
    SYSTEM_RAG_PROMPT
)

from backend.core.config import settings
from backend.embeddings.vectorizer import embedding_service

from backend.rag.srag.context_builder import (
    build_context,
    build_sources,
)

from backend.rag.srag.models import (
    EvidenceChunk,
    SRAGResult,
)

from backend.rag.srag.query_rewriter import (
    QueryRewriter,
)

from backend.rag.srag.validators import (
    SRAGValidators,
)

from backend.storage.vector_store import (
    vector_store,
)


logger = logging.getLogger(__name__)


REFUSAL_TEXT = (
    "I cannot answer this question based on "
    "the provided documents."
)


class SRAGEngine:

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

        self.max_retrieval_attempts = min(
            int(getattr(
                settings,
                "SRAG_MAX_RETRIEVAL_ATTEMPTS",
                1
            )),
            1
        )

        self.max_rewrite_attempts = 0

        self.max_support_revisions = 0

        self.initial_retrieval_k = max(
            int(getattr(
                settings,
                "SRAG_RETRIEVAL_CANDIDATES",
                12
            )),
            12
        )

        self.relevance_min_similarity = float(
            getattr(
                settings,
                "SRAG_MIN_SIMILARITY",
                0.20
            )
        )

        self.final_context_k = max(
            int(getattr(
                settings,
                "SRAG_CONTEXT_CHUNKS",
                6
            )),
            4
        )

    # =========================================================
    # ERROR HANDLING
    # =========================================================

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:

        text = str(exc).lower()

        return (
            "429" in text
            or "rate limit" in text
            or "resource exhausted" in text
            or "too many requests" in text
            or "quota" in text
        )

    @staticmethod
    def _safe_failure(
        retrieval_query: str,
        retrieval_attempts: int,
        support_revisions: int,
        rewrite_attempts: int,
        sources=None,
        status: str = "llm_error"
    ) -> SRAGResult:

        return SRAGResult(
            answer=REFUSAL_TEXT,
            sources=sources if sources is not None else [],
            retrieval_query=retrieval_query,
            retrieval_attempts=retrieval_attempts,
            support_revisions=support_revisions,
            rewrite_attempts=rewrite_attempts,
            status=status,
            refusal=True
        )

    # =========================================================
    # CONVERSATIONAL
    # =========================================================

    @staticmethod
    def _is_conversational(
        question: str
    ) -> bool:

        normalized = re.sub(
            r"[^a-z0-9\s]",
            "",
            question.lower()
        ).strip()

        normalized = re.sub(
            r"\s+",
            " ",
            normalized
        )

        patterns = [

            # English greetings
            r"^(hi|hello|hey)$",

            # Roman Urdu / Islamic greetings
            r"^(aoa|a oa|salam|salaam)$",
            r"^(assalamualaikum|assalam o alaikum)$",
            r"^(assalam alaikum|asalamualaikum)$",

            # Thanks
            r"^(thanks|thank you|thx|thankyou)$",

            # Capability questions
            r"^(what can you do)$",
            r"^(what are you able to do)$",
            r"^(how can you help)$",

            # Asking permission to ask questions
            r"^can i ask a question$",
            r"^can i ask questions$",
            r"^can i ask questions from the documents$",
            r"^can i ask questions about the documents$",
            r"^can i ask questions from my documents$",
            r"^can i ask you questions$",

            # Simple conversational phrases
            r"^how are you$",
            r"^how are you doing$",
            r"^are you there$",
        ]

        return any(
            re.match(
                pattern,
                normalized
            )
            for pattern in patterns
        )

    # =========================================================
    # CONVERSATIONAL ANSWER
    # =========================================================

    def _generate_conversational(
        self,
        question: str
    ) -> str:

        system = """
You are DocuChat.

Answer this simple conversational message
naturally and briefly.

If asked what you can do, explain that you
answer questions using the user's uploaded
documents.

Do not invent document facts.
""".strip()

        return self.generator._complete(
            question,
            system_prompt=system,
            max_tokens=150
        )

    # =========================================================
    # NORMALIZE
    # =========================================================

    @staticmethod
    def _normalize_chunks(
        raw_chunks: List[dict]
    ) -> List[EvidenceChunk]:

        output = []

        for index, item in enumerate(raw_chunks or []):

            content = str(
                item.get(
                    "content",
                    ""
                )
            ).strip()

            if not content:
                continue

            metadata = (
                item.get(
                    "metadata",
                    {}
                )
                or {}
            )

            if not isinstance(metadata, dict):
                metadata = {}

            try:
                similarity = float(
                    item.get(
                        "similarity",
                        0.0
                    )
                )
            except Exception:
                similarity = 0.0

            output.append(
                EvidenceChunk(
                    chunk_id=str(
                        item.get(
                            "id",
                            f"retrieved-{index}"
                        )
                    ),
                    document_id=str(
                        item.get(
                            "document_id",
                            ""
                        )
                    ),
                    content=content,
                    metadata=metadata,
                    similarity=similarity
                )
            )

        return output

    # =========================================================
    # DEDUPLICATE
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
    # STRUCTURED QUERY
    # =========================================================

    @staticmethod
    def _extract_constraints(
        question: str
    ) -> Dict[str, str]:

        constraints = {}

        patterns = {
            "week": r"\bweek\s+(\d+)\b",
            "day": r"\bday\s+(\d+)\b",
            "chapter": r"\bchapter\s+(\d+)\b",
            "section": r"\bsection\s+(\d+)\b",
            "module": r"\bmodule\s+(\d+)\b",
            "unit": r"\bunit\s+(\d+)\b",
            "part": r"\bpart\s+(\d+)\b",
        }

        for key, pattern in patterns.items():

            match = re.search(
                pattern,
                question,
                re.IGNORECASE
            )

            if match:
                constraints[key] = match.group(1)

        return constraints

    # =========================================================
    # HIERARCHY MATCH
    # =========================================================

    @classmethod
    def _hierarchy_score(
        cls,
        question: str,
        chunk: EvidenceChunk
    ) -> int:

        constraints = cls._extract_constraints(
            question
        )

        if not constraints:
            return 0

        metadata = chunk.metadata or {}

        hierarchy_values = []

        for key in (
            "breadcrumbs",
            "breadcrumb",
            "hierarchy",
            "section_path",
            "header_context",
        ):

            value = metadata.get(key)

            if value:
                hierarchy_values.append(
                    str(value)
                )

        hierarchy_values.append(
            chunk.content
        )

        hierarchy = " ".join(
            hierarchy_values
        ).lower()

        score = 0

        for key, value in constraints.items():

            patterns = [
                rf"\b{re.escape(key)}\s+{re.escape(value)}\b",
            ]

            if any(
                re.search(
                    pattern,
                    hierarchy,
                    re.IGNORECASE
                )
                for pattern in patterns
            ):
                score += 10

        return score

    # =========================================================
    # LOCAL RELEVANCE
    # =========================================================

    @classmethod
    def _local_relevance_score(
        cls,
        question: str,
        chunk: EvidenceChunk
    ) -> float:

        question_words = set(
            re.findall(
                r"\b[a-z0-9]+\b",
                question.lower()
            )
        )

        text = " ".join([
            str(chunk.content or ""),
            str(
                (chunk.metadata or {}).get(
                    "breadcrumbs",
                    ""
                )
            ),
            str(
                (chunk.metadata or {}).get(
                    "hierarchy",
                    ""
                )
            ),
        ]).lower()

        text_words = set(
            re.findall(
                r"\b[a-z0-9]+\b",
                text
            )
        )

        overlap = (
            len(
                question_words & text_words
            )
            / max(
                len(question_words),
                1
            )
        )

        hierarchy = cls._hierarchy_score(
            question,
            chunk
        )

        return (
            float(chunk.similarity) * 100.0
            + overlap * 20.0
            + hierarchy
        )

    # =========================================================
    # RETRIEVE
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
            query_text=query,
        )

        chunks = self._normalize_chunks(
            raw
        )

        return self._deduplicate(
            chunks
        )

    # =========================================================
    # SELECT RELEVANT
    # =========================================================

    def _select_relevant(
        self,
        question: str,
        chunks: List[EvidenceChunk]
    ) -> List[EvidenceChunk]:

        if not chunks:
            return []

        candidates = [
            chunk
            for chunk in chunks
            if chunk.similarity
            >= self.relevance_min_similarity
        ]

        if not candidates:
            return []

        constraints = self._extract_constraints(
            question
        )

        # -----------------------------------------------------
        # IMPORTANT:
        # For structured questions such as:
        # "What is in week 3 day 4?"
        #
        # Prefer exact hierarchy matches.
        # -----------------------------------------------------

        if constraints:

            exact = [
                chunk
                for chunk in candidates
                if self._hierarchy_score(
                    question,
                    chunk
                ) >= (
                    len(constraints) * 10
                )
            ]

            if exact:

                exact.sort(
                    key=lambda chunk: (
                        self._local_relevance_score(
                            question,
                            chunk
                        ),
                        chunk.similarity
                    ),
                    reverse=True
                )

                return exact[
                    :self.final_context_k
                ]

        # -----------------------------------------------------
        # Normal semantic question.
        # -----------------------------------------------------

        candidates.sort(
            key=lambda chunk: (
                self._local_relevance_score(
                    question,
                    chunk
                ),
                chunk.similarity
            ),
            reverse=True
        )

        return candidates[
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

        if not context:
            return REFUSAL_TEXT

        system = SYSTEM_RAG_PROMPT.format(
            context_block=context
        )

        return self.generator._complete(
            question,
            system_prompt=system,
            max_tokens=1800
        )

    # =========================================================
    # MAIN
    # =========================================================

    def answer(
        self,
        question: str,
        user_id: str,
        conversation=None
    ) -> SRAGResult:

        question = (
            question or ""
        ).strip()

        conversation = (
            conversation or []
        )

        if not question:

            return SRAGResult(
                answer=REFUSAL_TEXT,
                sources=[],
                retrieval_query="",
                retrieval_attempts=0,
                support_revisions=0,
                rewrite_attempts=0,
                status="empty_question",
                refusal=True
            )

        # -----------------------------------------------------
        # Conversational path
        #
        # This is intentionally separate so "Hi" does not
        # consume retrieval/validation calls.
        # -----------------------------------------------------

        if self._is_conversational(
            question
        ):

            try:

                answer = (
                    self._generate_conversational(
                        question
                    )
                    .strip()
                )

            except Exception as exc:

                if self._is_rate_limit_error(
                    exc
                ):

                    logger.error(
                        "Gemini rate limit reached "
                        "during conversational response."
                    )

                    return self._safe_failure(
                        retrieval_query="",
                        retrieval_attempts=0,
                        support_revisions=0,
                        rewrite_attempts=0,
                        status="llm_rate_limited"
                    )

                logger.exception(
                    "Conversational generation failed: %s",
                    exc
                )

                answer = (
                    "I can answer questions "
                    "based on your uploaded "
                    "documents."
                )

            return SRAGResult(
                answer=answer,
                sources=[],
                retrieval_query="",
                retrieval_attempts=0,
                support_revisions=0,
                rewrite_attempts=0,
                status="direct_conversational",
                refusal=False
            )

        # -----------------------------------------------------
        # IMPORTANT:
        #
        # Only ONE retrieval attempt.
        # No Gemini query rewrite loop.
        # -----------------------------------------------------

        # -----------------------------------------------------
        # DETERMINISTIC QUERY NORMALIZATION
        #
        # Resolve contextual references such as:
        #   "What is after that?"
        # using the previous conversation before embedding/retrieval.
        # No LLM call is made here.
        # -----------------------------------------------------

        retrieval_query = self.query_rewriter.rewrite(
            question=question,
            conversation=conversation,
            previous_query="",
            reason="initial_deterministic_normalization"
        )

        if not retrieval_query:
            retrieval_query = question

        logger.info(
            "SRAG retrieval query: '%s' -> '%s'",
            question,
            retrieval_query
        )

        retrieval_attempts = 1
        rewrite_attempts = 0
        support_revisions = 0

        last_chunks = []
        last_relevant = []

        # -----------------------------------------------------
        # RETRIEVAL
        # -----------------------------------------------------

        try:

            last_chunks = self._retrieve(
                retrieval_query,
                user_id
            )

            last_relevant = (
                self._select_relevant(
                    retrieval_query,
                    last_chunks
                )
            )

        except Exception as exc:

            logger.exception(
                "SRAG retrieval failed: %s",
                exc
            )

            return self._safe_failure(
                retrieval_query=retrieval_query,
                retrieval_attempts=retrieval_attempts,
                support_revisions=0,
                rewrite_attempts=0,
                status="retrieval_failed"
            )

        # -----------------------------------------------------
        # NO EVIDENCE
        # -----------------------------------------------------

        if not last_relevant:

            return SRAGResult(
                answer=REFUSAL_TEXT,
                sources=build_sources(
                    last_chunks
                ),
                retrieval_query=retrieval_query,
                retrieval_attempts=retrieval_attempts,
                support_revisions=0,
                rewrite_attempts=0,
                status="no_relevant_evidence",
                refusal=True
            )

        # -----------------------------------------------------
        # GEMINI CALL #1
        #
        # Generate answer.
        # -----------------------------------------------------

        try:

            answer = (
                self._generate(
                    retrieval_query,
                    last_relevant
                )
                .strip()
            )

        except Exception as exc:

            if self._is_rate_limit_error(
                exc
            ):

                logger.error(
                    "Gemini rate limit reached "
                    "during answer generation. "
                    "No retry will be attempted."
                )

                return self._safe_failure(
                    retrieval_query=retrieval_query,
                    retrieval_attempts=retrieval_attempts,
                    support_revisions=0,
                    rewrite_attempts=0,
                    sources=build_sources(
                        last_relevant
                    ),
                    status="llm_rate_limited"
                )

            logger.exception(
                "SRAG generation failed: %s",
                exc
            )

            return self._safe_failure(
                retrieval_query=retrieval_query,
                retrieval_attempts=retrieval_attempts,
                support_revisions=0,
                rewrite_attempts=0,
                sources=build_sources(
                    last_relevant
                ),
                status="generation_failed"
            )

        if not answer:
            answer = REFUSAL_TEXT

        # -----------------------------------------------------
        # If generator already refused, don't spend another
        # Gemini request validating a refusal.
        # -----------------------------------------------------

        if (
            answer.strip().lower()
            == REFUSAL_TEXT.lower()
        ):

            return SRAGResult(
                answer=REFUSAL_TEXT,
                sources=build_sources(
                    last_relevant
                ),
                retrieval_query=retrieval_query,
                retrieval_attempts=retrieval_attempts,
                support_revisions=0,
                rewrite_attempts=0,
                status="safe_refusal",
                refusal=True
            )

        # -----------------------------------------------------
        # GEMINI CALL #2
        #
        # ONE support validation only.
        #
        # No revision.
        # No re-validation.
        # No usefulness call.
        # No rewrite.
        # -----------------------------------------------------

        try:

            support = self.validators.support(
                retrieval_query,
                answer,
                build_context(
                    last_relevant
                )
            )

        except Exception as exc:

            if self._is_rate_limit_error(
                exc
            ):

                logger.error(
                    "Gemini rate limit reached "
                    "during support validation. "
                    "No retry will be attempted."
                )

                return self._safe_failure(
                    retrieval_query=retrieval_query,
                    retrieval_attempts=retrieval_attempts,
                    support_revisions=0,
                    rewrite_attempts=0,
                    sources=build_sources(
                        last_relevant
                    ),
                    status="llm_rate_limited"
                )

            logger.exception(
                "SRAG support validation failed: %s",
                exc
            )

            return self._safe_failure(
                retrieval_query=retrieval_query,
                retrieval_attempts=retrieval_attempts,
                support_revisions=0,
                rewrite_attempts=0,
                sources=build_sources(
                    last_relevant
                ),
                status="support_validation_failed"
            )

        status = support.get(
            "status"
        )

        # -----------------------------------------------------
        # FULLY SUPPORTED
        # -----------------------------------------------------

        if status == "fully_supported":

            return SRAGResult(
                answer=answer,
                sources=build_sources(
                    last_relevant
                ),
                retrieval_query=retrieval_query,
                retrieval_attempts=retrieval_attempts,
                support_revisions=0,
                rewrite_attempts=0,
                status="success",
                refusal=False
            )

        # -----------------------------------------------------
        # PARTIAL / NO SUPPORT
        #
        # IMPORTANT:
        # Do NOT call Gemini again.
        # Fail closed.
        # -----------------------------------------------------

        return SRAGResult(
            answer=REFUSAL_TEXT,
            sources=build_sources(
                last_relevant
            ),
            retrieval_query=retrieval_query,
            retrieval_attempts=retrieval_attempts,
            support_revisions=0,
            rewrite_attempts=0,
            status=(
                "partially_supported"
                if status == "partially_supported"
                else "no_support"
            ),
            refusal=True
        )