import re
from typing import Any


# ============================================================
# HEADER / HIERARCHY DETECTION
# ============================================================

WEEK_RE = re.compile(
    r"^(?:[#>\-\*\u2022\u25cf\u25aa\u25e6]\s*)?"
    r"week\s+(\d+)\b(.*)$",
    re.IGNORECASE,
)

DAY_RE = re.compile(
    r"^(?:[#>\-\*\u2022\u25cf\u25aa\u25e6]\s*)?"
    r"day\s+(\d+)\b(.*)$",
    re.IGNORECASE,
)

MODULE_RE = re.compile(
    r"^(?:[#>\-\*\u2022\u25cf\u25aa\u25e6]\s*)?"
    r"module\s+(\d+)\b(.*)$",
    re.IGNORECASE,
)

CHAPTER_RE = re.compile(
    r"^(?:[#>\-\*\u2022\u25cf\u25aa\u25e6]\s*)?"
    r"chapter\s+(\d+)\b(.*)$",
    re.IGNORECASE,
)

UNIT_RE = re.compile(
    r"^(?:[#>\-\*\u2022\u25cf\u25aa\u25e6]\s*)?"
    r"unit\s+(\d+)\b(.*)$",
    re.IGNORECASE,
)

PART_RE = re.compile(
    r"^(?:[#>\-\*\u2022\u25cf\u25aa\u25e6]\s*)?"
    r"part\s+(\d+)\b(.*)$",
    re.IGNORECASE,
)

SECTION_RE = re.compile(
    r"^(?:[#>\-\*\u2022\u25cf\u25e6]\s*)?"
    r"section\s+(\d+)\b(.*)$",
    re.IGNORECASE,
)


def _clean_header(line: str) -> str:
    """
    Removes common markdown/list prefixes while preserving
    the actual structural heading.
    """
    line = line.strip()

    line = re.sub(
        r"^[•●▪◦\-\*]\s*",
        "",
        line,
    )

    line = re.sub(
        r"^#{1,6}\s*",
        "",
        line,
    )

    line = re.sub(
        r"^>\s*",
        "",
        line,
    )

    return line.strip()


def _header_type(line: str) -> str | None:
    """
    Returns the structural type of a line.

    Possible values:
        week
        day
        module
        chapter
        unit
        part
        section
        markdown
        None
    """

    cleaned = _clean_header(line)

    if not cleaned:
        return None

    if len(cleaned) > 120:
        return None

    if WEEK_RE.match(cleaned):
        return "week"

    if DAY_RE.match(cleaned):
        return "day"

    if MODULE_RE.match(cleaned):
        return "module"

    if CHAPTER_RE.match(cleaned):
        return "chapter"

    if UNIT_RE.match(cleaned):
        return "unit"

    if PART_RE.match(cleaned):
        return "part"

    if SECTION_RE.match(cleaned):
        return "section"

    # Markdown headings that are not already covered above.
    if re.match(r"^#{1,6}\s+.+", line.strip()):
        return "markdown"

    # Do not infer plain-text lines such as "Services:",
    # "Employees:", or bullet items as structural headings.
    #
    # PDF extraction usually removes font-size/bold information, so
    # a generic title heuristic is unsafe. It can classify legitimate
    # list items such as "Web Development" as headings and create tiny
    # blocks that were previously discarded.
    return None


def is_header_line(line: str) -> bool:
    """
    Detect structural headings.

    Examples:
        Week 5
        Week 5: Integrations
        Day 2: Webhooks, HTTP & Scheduling
        Day 3: ...
        Module 1
        Chapter 2
        Section 4
        # Heading
        ## Heading
    """
    return _header_type(line) is not None


# ============================================================
# NUMBER EXTRACTION
# ============================================================

def _extract_number(pattern: re.Pattern, text: str) -> int | None:
    match = pattern.match(_clean_header(text))

    if not match:
        return None

    try:
        return int(match.group(1))
    except (ValueError, TypeError):
        return None


# ============================================================
# HIERARCHY STATE
# ============================================================

def _new_hierarchy() -> dict[str, Any]:
    return {
        "week_number": None,
        "week_title": "",
        "day_number": None,
        "day_title": "",
        "module_number": None,
        "module_title": "",
        "chapter_number": None,
        "chapter_title": "",
        "unit_number": None,
        "unit_title": "",
        "part_number": None,
        "part_title": "",
        "section_number": None,
        "section_title": "",
        "other_headers": [],
    }


def _reset_lower_hierarchy(
    hierarchy: dict[str, Any],
    level: str,
) -> None:
    """
    When a parent hierarchy changes, clear child hierarchy.

    Example:

        Week 5
        Day 2
        Section 1

        Week 6

    Week 6 must not inherit Day 2 / Section 1.
    """

    levels = [
        "week",
        "module",
        "chapter",
        "unit",
        "part",
        "day",
        "section",
    ]

    try:
        index = levels.index(level)
    except ValueError:
        return

    for child in levels[index + 1:]:
        hierarchy[f"{child}_number"] = None
        hierarchy[f"{child}_title"] = ""


def _update_hierarchy(
    hierarchy: dict[str, Any],
    header: str,
) -> None:
    """
    Update hierarchy from one structural header.
    """

    cleaned = _clean_header(header)
    header_type = _header_type(header)

    if not header_type:
        return

    if header_type == "week":
        match = WEEK_RE.match(cleaned)

        if match:
            number = int(match.group(1))
            title = match.group(2).strip(" \t:-–—")

            _reset_lower_hierarchy(
                hierarchy,
                "week",
            )

            hierarchy["week_number"] = number
            hierarchy["week_title"] = title

        return

    if header_type == "day":
        match = DAY_RE.match(cleaned)

        if match:
            number = int(match.group(1))
            title = match.group(2).strip(" \t:-–—")

            # Day changes reset sections belonging to the previous day.
            hierarchy["day_number"] = number
            hierarchy["day_title"] = title

            hierarchy["section_number"] = None
            hierarchy["section_title"] = ""

        return

    if header_type == "module":
        match = MODULE_RE.match(cleaned)

        if match:
            number = int(match.group(1))
            title = match.group(2).strip(" \t:-–—")

            _reset_lower_hierarchy(
                hierarchy,
                "module",
            )

            hierarchy["module_number"] = number
            hierarchy["module_title"] = title

        return

    if header_type == "chapter":
        match = CHAPTER_RE.match(cleaned)

        if match:
            number = int(match.group(1))
            title = match.group(2).strip(" \t:-–—")

            _reset_lower_hierarchy(
                hierarchy,
                "chapter",
            )

            hierarchy["chapter_number"] = number
            hierarchy["chapter_title"] = title

        return

    if header_type == "unit":
        match = UNIT_RE.match(cleaned)

        if match:
            number = int(match.group(1))
            title = match.group(2).strip(" \t:-–—")

            _reset_lower_hierarchy(
                hierarchy,
                "unit",
            )

            hierarchy["unit_number"] = number
            hierarchy["unit_title"] = title

        return

    if header_type == "part":
        match = PART_RE.match(cleaned)

        if match:
            number = int(match.group(1))
            title = match.group(2).strip(" \t:-–—")

            _reset_lower_hierarchy(
                hierarchy,
                "part",
            )

            hierarchy["part_number"] = number
            hierarchy["part_title"] = title

        return

    if header_type == "section":
        match = SECTION_RE.match(cleaned)

        if match:
            number = int(match.group(1))
            title = match.group(2).strip(" \t:-–—")

            hierarchy["section_number"] = number
            hierarchy["section_title"] = title

        return

    # Markdown / generic titles.
    if header_type in {"markdown", "title"}:
        hierarchy["other_headers"] = (
            hierarchy.get("other_headers", [])[-3:]
            + [cleaned]
        )


# ============================================================
# HIERARCHY STRING
# ============================================================

def _build_breadcrumbs(
    hierarchy: dict[str, Any],
) -> str:
    parts = []

    if hierarchy.get("module_number") is not None:
        title = hierarchy.get("module_title", "")
        value = f"Module {hierarchy['module_number']}"

        if title:
            value += f": {title}"

        parts.append(value)

    if hierarchy.get("chapter_number") is not None:
        title = hierarchy.get("chapter_title", "")
        value = f"Chapter {hierarchy['chapter_number']}"

        if title:
            value += f": {title}"

        parts.append(value)

    if hierarchy.get("unit_number") is not None:
        title = hierarchy.get("unit_title", "")
        value = f"Unit {hierarchy['unit_number']}"

        if title:
            value += f": {title}"

        parts.append(value)

    if hierarchy.get("part_number") is not None:
        title = hierarchy.get("part_title", "")
        value = f"Part {hierarchy['part_number']}"

        if title:
            value += f": {title}"

        parts.append(value)

    if hierarchy.get("week_number") is not None:
        title = hierarchy.get("week_title", "")
        value = f"Week {hierarchy['week_number']}"

        if title:
            value += f": {title}"

        parts.append(value)

    if hierarchy.get("day_number") is not None:
        title = hierarchy.get("day_title", "")
        value = f"Day {hierarchy['day_number']}"

        if title:
            value += f": {title}"

        parts.append(value)

    if hierarchy.get("section_number") is not None:
        title = hierarchy.get("section_title", "")
        value = f"Section {hierarchy['section_number']}"

        if title:
            value += f": {title}"

        parts.append(value)

    return " > ".join(parts)


# ============================================================
# HIERARCHY METADATA
# ============================================================

def _hierarchy_metadata(
    hierarchy: dict[str, Any],
) -> dict[str, Any]:

    breadcrumbs = _build_breadcrumbs(
        hierarchy
    )

    return {
        "breadcrumbs": breadcrumbs,

        "week_number": hierarchy.get(
            "week_number"
        ),

        "week_title": hierarchy.get(
            "week_title",
            "",
        ),

        "day_number": hierarchy.get(
            "day_number"
        ),

        "day_title": hierarchy.get(
            "day_title",
            "",
        ),

        "module_number": hierarchy.get(
            "module_number"
        ),

        "module_title": hierarchy.get(
            "module_title",
            "",
        ),

        "chapter_number": hierarchy.get(
            "chapter_number"
        ),

        "chapter_title": hierarchy.get(
            "chapter_title",
            "",
        ),

        "unit_number": hierarchy.get(
            "unit_number"
        ),

        "unit_title": hierarchy.get(
            "unit_title",
            "",
        ),

        "part_number": hierarchy.get(
            "part_number"
        ),

        "part_title": hierarchy.get(
            "part_title",
            "",
        ),

        "section_number": hierarchy.get(
            "section_number"
        ),

        "section_title": hierarchy.get(
            "section_title",
            "",
        ),

        "other_headers": list(
            hierarchy.get(
                "other_headers",
                [],
            )
        ),
    }


# ============================================================
# RECURSIVE CHUNKING
# ============================================================

def recursive_character_split(
    text: str,
    chunk_size: int = 700,
    chunk_overlap: int = 150,
) -> list[str]:
    """
    Split text while attempting to preserve semantic boundaries.

    Order:
        paragraph
        line
        sentence
        word
        character

    The final character fallback prevents oversized chunks.
    """

    text = str(text or "").strip()

    if not text:
        return []

    if chunk_size <= 0:
        raise ValueError(
            "chunk_size must be greater than 0"
        )

    if chunk_overlap < 0:
        raise ValueError(
            "chunk_overlap cannot be negative"
        )

    if chunk_overlap >= chunk_size:
        chunk_overlap = max(
            0,
            chunk_size // 5,
        )

    separators = [
        "\n\n",
        "\n",
        ". ",
        "? ",
        "! ",
        "; ",
        ", ",
        " ",
        "",
    ]

    for separator in separators:

        if separator == "":
            step = max(
                1,
                chunk_size - chunk_overlap,
            )

            return [
                text[i:i + chunk_size].strip()
                for i in range(
                    0,
                    len(text),
                    step,
                )
                if text[i:i + chunk_size].strip()
            ]

        splits = text.split(separator)

        if all(
            len(part) <= chunk_size
            for part in splits
        ):
            break

    chunks = []

    current = []
    current_length = 0

    for split in splits:

        split = split.strip()

        if not split:
            continue

        addition_length = (
            len(split)
            + (
                len(separator)
                if current
                else 0
            )
        )

        if (
            current
            and current_length + addition_length > chunk_size
        ):
            completed = separator.join(
                current
            ).strip()

            if completed:
                chunks.append(
                    completed
                )

            # Preserve semantic overlap.
            overlap_items = []
            overlap_length = 0

            for item in reversed(current):

                extra = (
                    len(item)
                    + (
                        len(separator)
                        if overlap_items
                        else 0
                    )
                )

                if (
                    overlap_length + extra
                    > chunk_overlap
                ):
                    break

                overlap_items.insert(
                    0,
                    item,
                )

                overlap_length += extra

            current = overlap_items

            current_length = (
                len(separator).join(current)
                if False
                else (
                    sum(
                        len(x)
                        for x in current
                    )
                    + (
                        len(separator)
                        * max(
                            0,
                            len(current) - 1,
                        )
                    )
                )
            )

        current.append(split)

        current_length = (
            sum(
                len(x)
                for x in current
            )
            + (
                len(separator)
                * max(
                    0,
                    len(current) - 1,
                )
            )
        )

    if current:
        completed = separator.join(
            current
        ).strip()

        if completed:
            chunks.append(
                completed
            )

    return chunks


# ============================================================
# SECTION-AWARE BLOCK CREATION
# ============================================================

def _build_structured_blocks(
    raw_text: str,
    initial_hierarchy: dict[str, Any] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """
    Convert a page into smaller hierarchy-aware blocks.

    IMPORTANT:
    We do NOT scan the whole page and then apply the last
    header to every chunk.

    Instead, hierarchy is updated while reading each line.
    Therefore:

        Week 5
        Day 2
        content A
        content B
        Day 3
        content C

    becomes:

        Week 5 > Day 2 -> content A/B
        Week 5 > Day 3 -> content C
    """

    hierarchy = (
        dict(initial_hierarchy)
        if initial_hierarchy
        else _new_hierarchy()
    )

    blocks = []

    current_lines = []

    def flush_current() -> None:
        if not current_lines:
            return

        text = "\n".join(
            current_lines
        ).strip()

        if len(text) <= 0:
            current_lines.clear()
            return

        blocks.append(
            (
                text,
                dict(hierarchy),
            )
        )

        current_lines.clear()

    for raw_line in raw_text.splitlines():

        line = raw_line.strip()

        if not line:
            if current_lines:
                current_lines.append("")

            continue

        header_type = _header_type(
            line
        )

        if header_type:

            # Flush content belonging to the
            # previous hierarchy BEFORE updating it.
            flush_current()

            _update_hierarchy(
                hierarchy,
                line,
            )

            # Keep the actual header available
            # in the block so its meaning is not lost.
            current_lines.append(
                _clean_header(line)
            )

            continue

        current_lines.append(
            line
        )

    flush_current()

    return blocks


# ============================================================
# MAIN DOCUMENT CHUNKER
# ============================================================

def process_document_to_chunks(
    parsed_pages: list[dict],
    chunk_size: int = 700,
    chunk_overlap: int = 150,
) -> list[dict]:
    """
    Convert parsed document pages into hierarchy-aware chunks.

    Important properties:

    1. Week/Day hierarchy is tracked line-by-line.
    2. Plain-text headings and list items are kept as document content;
       they are never silently discarded because PDF formatting is lost.
    3. A Day 2 chunk cannot accidentally receive Day 3 metadata
       simply because Day 3 appeared later on the same page.
    3. Exact hierarchy is stored in metadata.
    4. Hierarchy is also injected into content before embedding.
    5. Page/source metadata is preserved.
    6. Cross-page hierarchy is preserved.
    7. No LLM calls are made here.
    8. No loops can consume Gemini/OpenRouter tokens.
    """

    final_chunks: list[dict] = []
    global_chunk_index = 0

    # Carry hierarchy across pages because a document section
    # may continue onto the next page without repeating
    # "Week X / Day Y".
    document_hierarchy = _new_hierarchy()

    for page_index, page in enumerate(
        parsed_pages or []
    ):

        if not isinstance(page, dict):
            continue

        raw_text = str(
            page.get(
                "content",
                "",
            )
            or ""
        ).strip()

        if not raw_text:
            continue

        original_metadata = dict(
            page.get(
                "metadata",
                {},
            )
            or {}
        )

        # Build hierarchy-aware blocks.
        structured_blocks = (
            _build_structured_blocks(
                raw_text,
                initial_hierarchy=document_hierarchy,
            )
        )

        # Update carried hierarchy from the last block.
        if structured_blocks:
            document_hierarchy = dict(
                structured_blocks[-1][1]
            )

        for block_index, (
            block_text,
            hierarchy,
        ) in enumerate(
            structured_blocks
        ):

            if not block_text.strip():
                continue

            hierarchy_data = (
                _hierarchy_metadata(
                    hierarchy
                )
            )

            breadcrumbs = hierarchy_data.get(
                "breadcrumbs",
                "",
            )

            text_chunks = (
                recursive_character_split(
                    block_text,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
            )

            for chunk_index, chunk in enumerate(
                text_chunks
            ):

                chunk = chunk.strip()

                # ------------------------------------------------
                # EMBEDDING CONTENT
                # ------------------------------------------------

                if breadcrumbs:

                    context_prefix = (
                        "[Header Context: "
                        f"{breadcrumbs}"
                        "]\n"
                    )

                    enriched_content = (
                        context_prefix
                        + chunk
                    )

                else:
                    enriched_content = chunk

                # ------------------------------------------------
                # METADATA
                # ------------------------------------------------

                chunk_metadata = (
                    original_metadata.copy()
                )

                chunk_metadata.update(
                    hierarchy_data
                )

                # Useful deterministic identifiers.
                chunk_metadata[
                    "page_index"
                ] = page_index

                chunk_metadata[
                    "block_index"
                ] = block_index

                chunk_metadata[
                    "chunk_index"
                ] = chunk_index

                chunk_metadata[
                    "global_chunk_index"
                ] = global_chunk_index

                global_chunk_index += 1

                # Explicit hierarchy key.
                chunk_metadata[
                    "hierarchy"
                ] = breadcrumbs

                # These aliases make retrieval code easier
                # to support without breaking existing metadata.
                if (
                    hierarchy_data.get(
                        "week_number"
                    )
                    is not None
                ):
                    chunk_metadata[
                        "week"
                    ] = hierarchy_data[
                        "week_number"
                    ]

                if (
                    hierarchy_data.get(
                        "day_number"
                    )
                    is not None
                ):
                    chunk_metadata[
                        "day"
                    ] = hierarchy_data[
                        "day_number"
                    ]

                final_chunks.append(
                    {
                        "content": enriched_content,
                        "metadata": chunk_metadata,
                    }
                )

    return final_chunks