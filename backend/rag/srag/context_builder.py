from typing import Any, Dict, List


def build_context(chunks) -> str:

    if not chunks:
        return ""


    blocks = []

    for index, chunk in enumerate(
        chunks,
        start=1
    ):

        if hasattr(
            chunk,
            "content"
        ):

            content = chunk.content
            metadata = (
                chunk.metadata
                or {}
            )
            similarity = (
                chunk.similarity
            )

        else:

            content = str(
                chunk.get(
                    "content",
                    ""
                )
            )

            metadata = (
                chunk.get(
                    "metadata",
                    {}
                )
                or {}
            )

            similarity = float(
                chunk.get(
                    "similarity",
                    0.0
                )
            )

        source = metadata.get(
            "source",
            "Unknown Document"
        )

        page = metadata.get(
            "page",
            "Unknown"
        )

        breadcrumbs = metadata.get(
            "breadcrumbs",
            ""
        )

        header = (
            f"[EVIDENCE {index}]\n"
            f"Source: {source}\n"
            f"Page: {page}\n"
            f"Similarity: {similarity:.4f}"
        )

        if breadcrumbs:
            header += (
                f"\nHierarchy: {breadcrumbs}"
            )

        blocks.append(
            f"{header}\n"
            f"Content:\n{content}"
        )

    return (
        "\n\n"
        "=============================="
        "\n\n"
    ).join(blocks)


def build_sources(chunks) -> List[
    Dict[str, Any]
]:

    sources = []

    seen = set()

    for chunk in chunks or []:

        if hasattr(
            chunk,
            "document_id"
        ):

            document_id = (
                chunk.document_id
            )

            content = chunk.content
            metadata = (
                chunk.metadata
                or {}
            )

            similarity = (
                chunk.similarity
            )

        else:

            document_id = str(
                chunk.get(
                    "document_id",
                    ""
                )
            )

            content = chunk.get(
                "content",
                ""
            )

            metadata = (
                chunk.get(
                    "metadata",
                    {}
                )
                or {}
            )

            similarity = float(
                chunk.get(
                    "similarity",
                    0.0
                )
            )

        source = metadata.get(
            "source",
            "Unknown Document"
        )

        page = metadata.get(
            "page",
            "Unknown"
        )

        key = (
            document_id,
            source,
            page
        )

        if key in seen:
            continue

        seen.add(key)

        sources.append({

            "document_id":
                document_id,

            "source":
                source,

            "page":
                page,

            "content":
                content,

            "similarity":
                similarity,

            "breadcrumbs":
                metadata.get(
                    "breadcrumbs",
                    ""
                )
        })

    return sources