import json
import logging
import re
from typing import Any, Dict


logger = logging.getLogger(__name__)


class SRAGValidators:

    def __init__(
        self,
        client,
        model_name: str
    ):

        self.client = client
        self.model_name = model_name

    # =========================================================
    # JSON PARSER
    # =========================================================

    @staticmethod
    def _parse_json(
        text: str
    ) -> Dict[str, Any]:

        if not text:
            return {}

        text = text.strip()

        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"\s*```$",
            "",
            text
        )

        try:

            parsed = json.loads(
                text
            )

            if isinstance(
                parsed,
                dict
            ):
                return parsed

        except Exception:
            pass

        match = re.search(
            r"\{.*\}",
            text,
            flags=re.DOTALL
        )

        if match:

            try:

                parsed = json.loads(
                    match.group(0)
                )

                if isinstance(
                    parsed,
                    dict
                ):
                    return parsed

            except Exception:
                pass

        return {}

    # =========================================================
    # LLM CALL
    #
    # This is ONLY used for final support validation.
    # Relevance no longer calls Gemini.
    # =========================================================

    def _call(
        self,
        system_prompt: str,
        user_prompt: str,
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
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ],
                temperature=0.0,
                max_tokens=max_tokens,
                timeout=30.0
            )
        )

        raw = (
            response
            .choices[0]
            .message
            .content
            or ""
        )

        return self._parse_json(
            raw
        )

    # =========================================================
    # RELEVANCE
    #
    # NO GEMINI CALL.
    #
    # This method is retained so the existing SRAGEngine
    # interface does not break.
    # =========================================================

    @staticmethod
    def relevance(
        question: str,
        chunks
    ):

        if not chunks:
            return []

        question_words = set(
            re.findall(
                r"\b[a-z0-9]+\b",
                question.lower()
            )
        )

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

        scored = []

        for chunk in chunks:

            metadata = (
                chunk.metadata
                or {}
            )

            hierarchy = " ".join([
                str(
                    metadata.get(
                        "breadcrumbs",
                        ""
                    )
                ),
                str(
                    metadata.get(
                        "breadcrumb",
                        ""
                    )
                ),
                str(
                    metadata.get(
                        "hierarchy",
                        ""
                    )
                ),
                str(
                    metadata.get(
                        "section_path",
                        ""
                    )
                ),
                str(
                    chunk.content
                    or ""
                )
            ]).lower()

            hierarchy_score = 0

            for key, value in constraints.items():

                if re.search(
                    rf"\b{re.escape(key)}\s+{re.escape(value)}\b",
                    hierarchy,
                    re.IGNORECASE
                ):
                    hierarchy_score += 100

            text_words = set(
                re.findall(
                    r"\b[a-z0-9]+\b",
                    hierarchy
                )
            )

            overlap = (
                len(
                    question_words
                    & text_words
                )
                / max(
                    len(question_words),
                    1
                )
            )

            score = (
                hierarchy_score
                + overlap * 20.0
                + float(
                    getattr(
                        chunk,
                        "similarity",
                        0.0
                    )
                ) * 10.0
            )

            scored.append(
                (
                    score,
                    chunk
                )
            )

        scored.sort(
            key=lambda item: item[0],
            reverse=True
        )

        # Only retain candidates that have some meaningful
        # lexical/hierarchy/similarity evidence.
        return [
            chunk
            for score, chunk in scored
            if score > 0
        ]

    # =========================================================
    # SUPPORT
    #
    # ONE Gemini call.
    # =========================================================

    def support(
        self,
        question: str,
        answer: str,
        context: str
    ) -> Dict[str, Any]:

        system = """
You are a strict factual-grounding validator
for a production document RAG system.

Determine whether the answer is completely
supported by the supplied evidence.

Return ONLY valid JSON:

{
  "status": "fully_supported",
  "unsupported_claims": []
}

Allowed status values:

- fully_supported
- partially_supported
- no_support

Rules:

1. Every factual claim must be supported by the evidence.
2. Do not use outside knowledge.
3. Do not reward plausible guesses.
4. A citation does not make an unsupported claim supported.
5. If one meaningful factual claim is unsupported,
   use partially_supported.
6. If the central answer is unsupported,
   use no_support.
7. Preserve exact Week/Day/Chapter/Section hierarchy.
8. If the question requests a specific hierarchy,
   evidence from another hierarchy is not acceptable.
9. Do not penalize harmless conversational wording.
""".strip()

        user = f"""
QUESTION:
{question}

ANSWER:
{answer}

EVIDENCE:
{context}

Return JSON only.
""".strip()

        result = self._call(
            system,
            user,
            max_tokens=500
        )

        status = result.get(
            "status"
        )

        if status not in {
            "fully_supported",
            "partially_supported",
            "no_support"
        }:
            status = "no_support"

        claims = result.get(
            "unsupported_claims",
            []
        )

        if not isinstance(
            claims,
            list
        ):
            claims = []

        return {
            "status": status,
            "unsupported_claims": [
                str(x)
                for x in claims[:10]
            ]
        }

    # =========================================================
    # USEFULNESS
    #
    # Kept for compatibility.
    #
    # IMPORTANT:
    # It does NOT call Gemini.
    # =========================================================

    @staticmethod
    def usefulness(
        question: str,
        answer: str
    ) -> Dict[str, Any]:

        if not answer:
            return {
                "isuse": "not_useful",
                "reason": "Empty answer."
            }

        refusal = (
            "I cannot answer this question based on "
            "the provided documents."
        )

        if (
            answer.strip().lower()
            == refusal.lower()
        ):
            return {
                "isuse": "useful",
                "reason": "Safe refusal."
            }

        return {
            "isuse": "useful",
            "reason": "Answer generated after evidence validation."
        }