import json
import logging
import re
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


class QueryRewriter:
    """
    Converts the user's natural-language question into
    a retrieval-optimized query.

    IMPORTANT:
    Query rewriting is an optimization, not a requirement.

    If rewriting fails, the original user query is returned.
    """

    def __init__(
        self,
        client,
        model_name: str
    ):
        self.client = client
        self.model_name = model_name

    # =========================================================
    # ROBUST JSON EXTRACTION
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

        # Remove markdown fences.
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

        # First attempt: complete response.
        try:
            value = json.loads(text)

            if isinstance(value, dict):
                return value

        except json.JSONDecodeError:
            pass

        # Second attempt: find the first JSON object.
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
    # REWRITE
    # =========================================================

    def rewrite(
        self,
        question: str,
        conversation: List[
            Dict[str, str]
        ] | None = None,
        previous_query: str = "",
        reason: str = "initial",
    ) -> str:

        conversation = (
            conversation
            or []
        )

        recent = conversation[-6:]

        history_text = "\n".join(
            f"{m.get('role', 'user').upper()}: "
            f"{m.get('content', '').strip()}"
            for m in recent
            if m.get(
                "content",
                ""
            ).strip()
        )

        prompt = f"""
You are the retrieval-query planner for an enterprise document assistant.

Your ONLY job is to rewrite the user's question into a better search query.

Do NOT answer the question.

Rules:

1. Preserve the user's exact intent.
2. Resolve pronouns using the conversation when possible.
3. Preserve names, dates, numbers, technical terms and proper nouns.
4. Add useful document terminology when appropriate.
5. Do not invent facts.
6. Keep the query concise.
7. Return ONLY valid JSON.
8. Do not use Markdown code fences.

Required JSON:

{{
  "retrieval_query": "search query here"
}}

Reason for rewrite:

{reason}

Conversation:

{history_text or "(none)"}

Original question:

{question}

Previous retrieval query:

{previous_query or "(none)"}
""".strip()

        try:

            response = (
                self.client
                .chat
                .completions
                .create(

                    model=self.model_name,

                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a "
                                "retrieval-query "
                                "rewriter."
                            )
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],

                    temperature=0,

                    max_tokens=150,

                    timeout=20.0,

                    # Ask compatible providers/models
                    # for JSON when supported.
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

            data = (
                self
                ._extract_json(raw)
            )

            query = str(
                data.get(
                    "retrieval_query",
                    ""
                )
            ).strip()

            query = re.sub(
                r"\s+",
                " ",
                query
            )

            words = query.split()

            if 2 <= len(words) <= 30:

                return query

            raise ValueError(
                "Generated retrieval query "
                "has an invalid length."
            )

        except Exception as exc:

            logger.warning(
                "Query rewrite failed; "
                "using original query. "
                "Reason: %s",
                exc
            )

            # IMPORTANT:
            # Rewriting must NEVER prevent retrieval.
            return re.sub(
                r"\s+",
                " ",
                question
            ).strip()