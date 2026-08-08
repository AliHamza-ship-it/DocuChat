import json
import logging
import re
from typing import Any, Dict, List

from backend.rag.models import EvidenceChunk


logger = logging.getLogger(__name__)


class SRAGValidators:
    """
    Validation layer for Self-RAG.

    Relevance validation is allowed to fall back to
    retrieval scores.

    Support validation remains fail-closed because
    factual grounding is the final safety boundary.
    """

    def __init__(
        self,
        client,
        model_name: str
    ):

        self.client = client
        self.model_name = model_name

    # =========================================================
    # JSON EXTRACTION
    # =========================================================

    @staticmethod
    def _extract_json(
        text: str
    ) -> Dict[str, Any]:

        if not text:
            raise ValueError(
                "Model returned an empty response."
            )

        text = text.strip()

        # Remove Markdown code fences.
        text = re.sub(
            r"```json\s*",
            "",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"```\s*$",
            "",
            text
        )

        text = text.strip()

        # Direct JSON.
        try:

            value = json.loads(text)

            if isinstance(
                value,
                dict
            ):
                return value

        except json.JSONDecodeError:
            pass

        # Extract JSON object.
        match = re.search(
            r"\{[\s\S]*\}",
            text
        )

        if match:

            candidate = (
                match.group(0)
                .strip()
            )

            try:

                value = json.loads(
                    candidate
                )

                if isinstance(
                    value,
                    dict
                ):
                    return value

            except json.JSONDecodeError:
                pass

        raise ValueError(
            "Model response did not contain valid JSON."
        )

    # =========================================================
    # LLM JSON CALL
    # =========================================================

    def _call_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 500
    ) -> Dict[str, Any]:

        response = (
            self.client
            .chat
            .completions
            .create(

                model=self.model_name,

                messages=[
                    {
                        "role": "system",
                        "content": system
                    },
                    {
                        "role": "user",
                        "content": user
                    }
                ],

                temperature=0,

                max_tokens=max_tokens,

                timeout=30.0,

                response_format={
                    "type": "json_object"
                },
            )
        )

        raw = (
            response
            .choices[0]
            .message
            .content
            or ""
        )

        return self._extract_json(
            raw
        )

    # =========================================================
    # IS RELEVANT
    # =========================================================

    def relevance(
        self,
        question: str,
        chunks: List[EvidenceChunk]
    ) -> List[EvidenceChunk]:

        if not chunks:
            return []

        evidence_text = "\n\n".join(
            chunk.to_context(index + 1)
            for index, chunk
            in enumerate(chunks)
        )

        system = """
You are a strict evidence relevance judge.

Determine which retrieved evidence chunks contain
information that could help answer the question.

Do not answer the question.

Do not use outside knowledge.

A chunk is relevant if it contains:
- the answer,
- a fact needed to construct the answer,
- or necessary context for the answer.

Return ONLY valid JSON:

{
  "relevant_indices": [1, 2]
}

If none are relevant:

{
  "relevant_indices": []
}
""".strip()

        user = (
            f"QUESTION:\n"
            f"{question}\n\n"
            f"EVIDENCE:\n"
            f"{evidence_text}"
        )

        try:

            data = self._call_json(
                system,
                user,
                max_tokens=300
            )

            indices = set()

            for value in (
                data.get(
                    "relevant_indices",
                    []
                )
                or []
            ):

                try:

                    index = int(
                        value
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    continue

                if 1 <= index <= len(
                    chunks
                ):

                    indices.add(
                        index
                    )

            relevant = [
                chunk
                for index, chunk
                in enumerate(
                    chunks,
                    start=1
                )
                if index in indices
            ]

            return relevant

        except Exception as exc:

            logger.warning(
                "Relevance validation "
                "failed; falling back to "
                "retrieval ranking. "
                "Reason: %s",
                exc
            )

            # -------------------------------------------------
            # IMPORTANT FALLBACK
            # -------------------------------------------------
            #
            # Retrieval already selected candidates using
            # semantic similarity.
            #
            # Do NOT turn a temporary judge failure into
            # "no evidence".
            #
            # The final IsSUP validator remains responsible
            # for factual grounding.
            # -------------------------------------------------

            return sorted(
                chunks,
                key=lambda x: (
                    x.similarity
                ),
                reverse=True
            )

    # =========================================================
    # ISSUP
    # =========================================================

    def support(
        self,
        question: str,
        answer: str,
        context: str
    ) -> Dict[str, Any]:

        system = """
You are the final factual-grounding validator
for an enterprise document RAG system.

Determine whether every MATERIAL factual claim
in the answer is supported by the supplied evidence.

Do not use outside knowledge.

Return ONLY valid JSON:

{
  "status": "fully_supported",
  "unsupported_claims": [],
  "evidence": []
}

Possible statuses:

fully_supported
partially_supported
no_support

Rules:

1. fully_supported:
   Every material factual claim is supported.

2. partially_supported:
   Some material claims are supported,
   but at least one is unsupported.

3. no_support:
   The answer cannot be supported by the evidence.

4. A citation-looking string is NOT evidence.

5. Check the actual evidence content.

6. Be conservative.

7. When uncertain, choose no_support.
""".strip()

        user = (
            f"QUESTION:\n"
            f"{question}\n\n"
            f"ANSWER:\n"
            f"{answer}\n\n"
            f"EVIDENCE:\n"
            f"{context}"
        )

        try:

            data = self._call_json(
                system,
                user,
                max_tokens=800
            )

            status = data.get(
                "status"
            )

            if status not in {
                "fully_supported",
                "partially_supported",
                "no_support"
            }:

                status = "no_support"

            return {

                "status": status,

                "unsupported_claims": (
                    data.get(
                        "unsupported_claims",
                        []
                    )
                    or []
                ),

                "evidence": (
                    data.get(
                        "evidence",
                        []
                    )
                    or []
                ),
            }

        except Exception as exc:

            logger.warning(
                "Support validation failed. "
                "Failing closed. "
                "Reason: %s",
                exc
            )

            return {

                "status": "no_support",

                "unsupported_claims": [
                    "Support validator failed."
                ],

                "evidence": [],
            }

    # =========================================================
    # ISUSE
    # =========================================================

    def usefulness(
        self,
        question: str,
        answer: str
    ) -> Dict[str, Any]:

        system = """
You judge whether an answer actually answers
the user's question.

Do not check external facts.

Return ONLY valid JSON:

{
  "isuse": "useful",
  "reason": "The answer directly addresses the question."
}

Possible values:

useful
not_useful
""".strip()

        user = (
            f"QUESTION:\n"
            f"{question}\n\n"
            f"ANSWER:\n"
            f"{answer}"
        )

        try:

            data = self._call_json(
                system,
                user,
                max_tokens=200
            )

            status = data.get(
                "isuse"
            )

            if status not in {
                "useful",
                "not_useful"
            }:

                status = "not_useful"

            return {

                "isuse": status,

                "reason": str(
                    data.get(
                        "reason",
                        ""
                    )
                )[:300]
            }

        except Exception as exc:

            logger.warning(
                "Usefulness validation "
                "failed; treating answer "
                "as not useful. "
                "Reason: %s",
                exc
            )

            return {

                "isuse": "not_useful",

                "reason": (
                    "Usefulness validator failed."
                )
            }