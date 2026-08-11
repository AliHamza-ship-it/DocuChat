import logging
import re
from typing import Dict, Optional, List, Tuple


logger = logging.getLogger(__name__)


class QueryRewriter:
    """
    Deterministic query normalizer for SRAG.

    IMPORTANT:
    - No LLM/Gemini/OpenRouter call is made here.
    - Explicit Week/Day/Chapter/etc. identifiers are preserved.
    - Conversational follow-ups such as:
        "What is after that?"
        "What comes next?"
        "What is the next day?"
        "What did we learn before that?"
      are resolved from the recent conversation.
    - The goal is to improve retrieval without introducing another
      token-consuming model call or probabilistic rewrite.
    """

    def __init__(
        self,
        client=None,
        model_name: str = ""
    ):
        # Kept for compatibility with the existing engine.
        # This class intentionally does NOT call the LLM.
        self.client = client
        self.model_name = model_name

    # =========================================================
    # NORMALIZATION
    # =========================================================

    @staticmethod
    def _normalize(text: str) -> str:
        if not text:
            return ""

        text = re.sub(
            r"\s+",
            " ",
            str(text)
        ).strip()

        return text[:1200]

    # =========================================================
    # STRUCTURED CONSTRAINTS
    # =========================================================

    @staticmethod
    def _extract_constraints(
        text: str
    ) -> Dict[str, str]:
        """
        Extract explicit hierarchical identifiers.

        Examples:
            Week 5 Day 2
            week 3
            day 4
            Chapter 2
            Section 7
        """

        text = text or ""

        patterns = {
            "week": r"\bweek\s+(\d+)\b",
            "day": r"\bday\s+(\d+)\b",
            "chapter": r"\bchapter\s+(\d+)\b",
            "section": r"\bsection\s+(\d+)\b",
            "module": r"\bmodule\s+(\d+)\b",
            "unit": r"\bunit\s+(\d+)\b",
            "part": r"\bpart\s+(\d+)\b",
        }

        constraints: Dict[str, str] = {}

        for key, pattern in patterns.items():
            match = re.search(
                pattern,
                text,
                flags=re.IGNORECASE
            )

            if match:
                constraints[key] = match.group(1)

        return constraints

    # =========================================================
    # CONVERSATION EXTRACTION
    # =========================================================

    @staticmethod
    def _conversation_items(
        conversation
    ) -> List[Tuple[str, str]]:
        """
        Convert the different conversation formats used by the
        application into a simple list of (role, content).

        Supported examples:

            {"role": "user", "content": "..."}
            {"role": "assistant", "content": "..."}
            {"question": "..."}
            {"answer": "..."}
        """

        if not conversation:
            return []

        result: List[Tuple[str, str]] = []

        for item in conversation:
            if item is None:
                continue

            if isinstance(item, dict):
                role = str(
                    item.get("role")
                    or item.get("type")
                    or ""
                ).lower().strip()

                content = (
                    item.get("content")
                    or item.get("message")
                    or item.get("text")
                    or ""
                )

                # Some history formats use question/answer.
                if not content:
                    if item.get("question"):
                        role = "user"
                        content = item.get("question")

                    elif item.get("answer"):
                        role = "assistant"
                        content = item.get("answer")

                content = QueryRewriter._normalize(
                    str(content)
                )

                if content:
                    result.append(
                        (role, content)
                    )

                continue

            # Fallback for simple string history.
            if isinstance(item, str):
                content = QueryRewriter._normalize(item)

                if content:
                    result.append(
                        ("", content)
                    )

        return result

    # =========================================================
    # FIND MOST RECENT STRUCTURED CONTEXT
    # =========================================================

    @classmethod
    def _find_previous_context(
        cls,
        conversation=None,
        previous_query: str = ""
    ) -> Dict[str, str]:
        """
        Find the most recent explicit hierarchical context.

        Priority:
            1. previous_query
            2. recent user messages
            3. recent conversation messages

        This deliberately searches backwards so the latest Week/Day
        reference wins.
        """

        candidates: List[str] = []

        if previous_query:
            candidates.append(
                cls._normalize(previous_query)
            )

        items = cls._conversation_items(
            conversation
        )

        # Search newest messages first.
        for role, content in reversed(items):
            if not content:
                continue

            # User messages are stronger evidence than assistant text.
            if role == "user":
                candidates.insert(
                    0,
                    content
                )

        # Then inspect everything else from newest to oldest.
        for role, content in reversed(items):
            if not content:
                continue

            if content not in candidates:
                candidates.append(content)

        merged: Dict[str, str] = {}

        # Most recent explicit values win independently.
        for text in candidates:
            constraints = cls._extract_constraints(text)

            for key, value in constraints.items():
                if key not in merged:
                    merged[key] = value

            # We have the most important hierarchy once both
            # week and day are available.
            if (
                "week" in merged
                and "day" in merged
            ):
                break

        return merged

    # =========================================================
    # FOLLOW-UP DETECTION
    # =========================================================

    @staticmethod
    def _is_after_followup(
        question: str
    ) -> bool:
        q = question.lower().strip()

        patterns = [
            r"\bafter\s+that\b",
            r"\bafter\s+this\b",
            r"\bwhat\s+comes\s+after\b",
            r"\bwhat\s+(?:is|was)\s+after\b",
            r"\bwhat\s+comes\s+next\b",
            r"\bwhat\s+is\s+next\b",
            r"\bwhat's\s+next\b",
            r"\bwhats\s+next\b",
            r"\bnext\s+day\b",
            r"\bfollowing\s+day\b",
            r"\bnext\s+one\b",
            r"\bwhat\s+was\s+next\b",
            r"\bwhat\s+did\s+we\s+learn\s+next\b",
            r"\bwhat\s+topics\s+were\s+next\b",
        ]

        return any(
            re.search(pattern, q)
            for pattern in patterns
        )

    @staticmethod
    def _is_before_followup(
        question: str
    ) -> bool:
        q = question.lower().strip()

        patterns = [
            r"\bbefore\s+that\b",
            r"\bbefore\s+this\b",
            r"\bwhat\s+comes\s+before\b",
            r"\bwhat\s+(?:is|was)\s+before\b",
            r"\bprevious\s+day\b",
            r"\bprior\s+day\b",
            r"\blast\s+day\b",
            r"\bwhat\s+was\s+before\b",
            r"\bwhat\s+did\s+we\s+learn\s+before\b",
        ]

        return any(
            re.search(pattern, q)
            for pattern in patterns
        )

    @staticmethod
    def _is_same_context_followup(
        question: str
    ) -> bool:
        """
        Follow-ups which still refer to the previous topic but do not
        explicitly say next/previous.

        Examples:
            "tell me more about that"
            "what topics were covered?"
            "what did we learn?"
        """

        q = question.lower().strip()

        patterns = [
            r"\babout\s+that\b",
            r"\babout\s+this\b",
            r"\bthat\s+topic\b",
            r"\bthis\s+topic\b",
            r"\bwhat\s+did\s+we\s+learn\b",
            r"\bwhat\s+was\s+covered\b",
            r"\bwhat\s+topics\s+were\s+covered\b",
            r"\btell\s+me\s+more\b",
        ]

        return any(
            re.search(pattern, q)
            for pattern in patterns
        )

    # =========================================================
    # STRUCTURED FOLLOW-UP RESOLUTION
    # =========================================================

    @classmethod
    def _resolve_followup(
        cls,
        question: str,
        conversation=None,
        previous_query: str = ""
    ) -> Optional[str]:
        """
        Deterministically resolve relative queries.

        Supports both:
          1. Explicit references:
             "What is after Week 5 Day 2?"
             -> "Week 5 Day 3"
          2. Conversational references:
             previous turn: "What is in Week 5 Day 2?"
             current: "What is after that?"
             -> "Week 5 Day 3"

        No LLM call is made.
        """
        q = cls._normalize(question)
        if not q:
            return None

        after = cls._is_after_followup(q)
        before = cls._is_before_followup(q)

        if not after and not before:
            return None

        # First use an explicit Week/Day/etc. reference in the CURRENT
        # question. This is stronger than conversational history.
        explicit = cls._extract_constraints(q)

        # Otherwise resolve "that/this/next/previous" against the latest
        # structured context from the conversation.
        context = explicit or cls._find_previous_context(
            conversation=conversation,
            previous_query=previous_query
        )

        if not context:
            return None

        week = context.get("week")
        day = context.get("day")

        # Week/Day is the strongest hierarchy for this training program.
        if week is not None and day is not None:
            try:
                week_number = int(week)
                day_number = int(day)
            except (TypeError, ValueError):
                return None

            if after:
                return f"Week {week_number} Day {day_number + 1}"

            if before:
                # Do not invent the previous week's day count. If Day 1
                # is requested, leave the query unresolved so retrieval
                # cannot hallucinate a nonexistent section.
                if day_number <= 1:
                    return None

                return f"Week {week_number} Day {day_number - 1}"

        # If only a week is known, preserve it rather than inventing a day.
        if week is not None:
            return f"Week {week}"

        if day is not None:
            try:
                day_number = int(day)
            except (TypeError, ValueError):
                return None

            if after:
                return f"Day {day_number + 1}"

            if before and day_number > 1:
                return f"Day {day_number - 1}"

        return None

    # =========================================================
    # SAME-CONTEXT FOLLOW-UP
    # =========================================================

    @classmethod
    def _resolve_same_context(
        cls,
        question: str,
        conversation=None,
        previous_query: str = ""
    ) -> Optional[str]:
        """
        Attach the latest structured context to a vague follow-up.

        Example:

            Previous:
                What is in Week 5 Day 2?

            Current:
                What topics were covered?

        Result:

            Week 5 Day 2 topics covered
        """

        if not cls._is_same_context_followup(question):
            return None

        context = cls._find_previous_context(
            conversation=conversation,
            previous_query=previous_query
        )

        if not context:
            return None

        prefix_parts = []

        if "week" in context:
            prefix_parts.append(
                f"Week {context['week']}"
            )

        if "day" in context:
            prefix_parts.append(
                f"Day {context['day']}"
            )

        if not prefix_parts:
            return None

        prefix = " ".join(prefix_parts)

        return cls._normalize(
            f"{prefix} {question}"
        )

    # =========================================================
    # PRESERVE EXPLICIT QUERY
    # =========================================================

    @classmethod
    def _preserve_explicit_constraints(
        cls,
        query: str,
        original_question: str
    ) -> str:
        """
        Never allow normalization to remove explicit structured
        identifiers from the user's current question.
        """

        query = cls._normalize(query)
        original_question = cls._normalize(
            original_question
        )

        original_constraints = cls._extract_constraints(
            original_question
        )

        if not original_constraints:
            return query

        for key, value in original_constraints.items():
            pattern = (
                rf"\b{re.escape(key)}\s+"
                rf"{re.escape(value)}\b"
            )

            if not re.search(
                pattern,
                query,
                flags=re.IGNORECASE
            ):
                query = (
                    f"{query} {key} {value}"
                ).strip()

        return cls._normalize(query)

    # =========================================================
    # FALLBACK
    # =========================================================

    @classmethod
    def _fallback_query(
        cls,
        question: str
    ) -> str:
        return cls._normalize(question)

    # =========================================================
    # MAIN REWRITE
    # =========================================================

    def rewrite(
        self,
        question: str,
        conversation=None,
        previous_query: str = "",
        reason: str = ""
    ) -> str:
        """
        Deterministic rewrite.

        Priority:
          1. Empty query -> empty
          2. Relative follow-up -> resolve target hierarchy
          3. Explicit structured query -> preserve unchanged
          4. Same-context follow-up -> attach previous hierarchy
          5. Safe normalized fallback

        The relative-follow-up step intentionally comes BEFORE the
        explicit-identifier preservation step so that:
            "What is after Week 5 Day 2?"
        becomes:
            "Week 5 Day 3"
        rather than remaining as the original query.
        """
        question = self._normalize(question)

        if not question:
            return ""

        # ---------------------------------------------------------
        # STEP 1: Relative follow-up.
        #
        # This must run first because a query can contain an explicit
        # Week/Day reference AND ask for a relative neighbor.
        # ---------------------------------------------------------
        resolved_followup = self._resolve_followup(
            question=question,
            conversation=conversation,
            previous_query=previous_query
        )

        if resolved_followup:
            logger.info(
                "Deterministic follow-up resolution: '%s' -> '%s'",
                question,
                resolved_followup
            )
            return self._normalize(resolved_followup)

        # ---------------------------------------------------------
        # STEP 2: Explicit structured query.
        #
        # Never alter already-working queries such as:
        # "What is in Week 5 Day 2?"
        # "What was covered in Week 3 Day 4?"
        # ---------------------------------------------------------
        explicit_constraints = self._extract_constraints(question)

        if explicit_constraints:
            return self._preserve_explicit_constraints(
                question,
                question
            )

        # ---------------------------------------------------------
        # STEP 3: Same-context follow-up.
        # ---------------------------------------------------------
        resolved_context = self._resolve_same_context(
            question=question,
            conversation=conversation,
            previous_query=previous_query
        )

        if resolved_context:
            logger.info(
                "Deterministic context resolution: '%s' -> '%s'",
                question,
                resolved_context
            )
            return self._normalize(resolved_context)

        # ---------------------------------------------------------
        # STEP 4: Safe fallback.
        # ---------------------------------------------------------
        return self._fallback_query(question)

    # =========================================================
    # LOCAL EXPANSION
    # =========================================================

    @classmethod
    def expand_locally(
        cls,
        question: str,
        conversation=None,
        previous_query: str = ""
    ) -> str:
        """
        Compatibility helper using the exact same deterministic rules
        as rewrite().
        """
        question = cls._normalize(question)

        if not question:
            return ""

        resolved_followup = cls._resolve_followup(
            question=question,
            conversation=conversation,
            previous_query=previous_query
        )

        if resolved_followup:
            return cls._normalize(resolved_followup)

        explicit_constraints = cls._extract_constraints(question)

        if explicit_constraints:
            return cls._preserve_explicit_constraints(
                question,
                question
            )

        resolved_context = cls._resolve_same_context(
            question=question,
            conversation=conversation,
            previous_query=previous_query
        )

        if resolved_context:
            return cls._normalize(resolved_context)

        return cls._fallback_query(question)