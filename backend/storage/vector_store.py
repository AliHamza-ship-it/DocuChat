import os
import json
import logging
import re
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
import faiss
from supabase import Client

from backend.database.supabase_client import get_supabase_client
from backend.core.config import settings


logger = logging.getLogger(__name__)


class VectorStoreManager:

    def __init__(self):

        self.dimension = (
            settings.EMBEDDING_DIMENSIONS
        )

        self.faiss_dir = os.path.join(
            os.path.dirname(__file__),
            "..",
            "faiss_index"
        )

        os.makedirs(
            self.faiss_dir,
            exist_ok=True
        )

        self.faiss_file_path = os.path.join(
            self.faiss_dir,
            "index.faiss"
        )

        self.meta_file_path = os.path.join(
            self.faiss_dir,
            "metadata.json"
        )

    # =========================================================
    # SUPABASE
    # =========================================================

    def _get_supabase(self) -> Client:
        return get_supabase_client()

    # =========================================================
    # TEXT HELPERS
    # =========================================================

    @staticmethod
    def _normalize_text(
        value: Any
    ) -> str:

        if value is None:
            return ""

        return re.sub(
            r"[^a-z0-9\s]",
            " ",
            str(value).lower()
        ).strip()

    @staticmethod
    def _tokens(
        value: Any
    ) -> set:

        normalized = (
            VectorStoreManager
            ._normalize_text(value)
        )

        return set(
            normalized.split()
        )

    @staticmethod
    def _metadata(
        item: Dict[str, Any]
    ) -> Dict[str, Any]:

        metadata = item.get(
            "metadata",
            {}
        )

        if not isinstance(
            metadata,
            dict
        ):
            return {}

        return metadata

    # =========================================================
    # STRUCTURED QUERY CONSTRAINTS
    # =========================================================

    @staticmethod
    def _extract_constraints(
        query: str
    ) -> Dict[str, str]:

        normalized = (
            VectorStoreManager
            ._normalize_text(query)
        )

        constraints = {}

        patterns = {

            "week":
                r"\bweek\s+(\d+)\b",

            "day":
                r"\bday\s+(\d+)\b",

            "chapter":
                r"\bchapter\s+(\d+)\b",

            "section":
                r"\bsection\s+(\d+)\b",

            "module":
                r"\bmodule\s+(\d+)\b",

            "unit":
                r"\bunit\s+(\d+)\b",

            "part":
                r"\bpart\s+(\d+)\b",
        }

        for key, pattern in patterns.items():

            match = re.search(
                pattern,
                normalized,
                re.IGNORECASE
            )

            if match:

                constraints[key] = (
                    match.group(1)
                )

        return constraints

    # =========================================================
    # HIERARCHY MATCH
    # =========================================================

    @classmethod
    def _hierarchy_match(
        cls,
        query: str,
        item: Dict[str, Any]
    ) -> Dict[str, Any]:

        constraints = (
            cls._extract_constraints(
                query
            )
        )

        if not constraints:

            return {
                "has_constraint": False,
                "matched": False,
                "score": 0.0,
                "matches": {}
            }

        metadata = cls._metadata(
            item
        )

        breadcrumbs = cls._normalize_text(
            metadata.get(
                "breadcrumbs",
                ""
            )
        )

        content = cls._normalize_text(
            item.get(
                "content",
                ""
            )
        )

        matches = {}

        for key, value in (
            constraints.items()
        ):

            metadata_value = metadata.get(
                key
            )

            if (
                metadata_value is not None
                and str(metadata_value)
                == str(value)
            ):

                matches[key] = True
                continue

            pattern = (
                rf"\b{key}\s+{re.escape(value)}\b"
            )

            if re.search(
                pattern,
                breadcrumbs,
                re.IGNORECASE
            ):

                matches[key] = True
                continue

            if re.search(
                pattern,
                content,
                re.IGNORECASE
            ):

                matches[key] = True
                continue

            matches[key] = False

        matched_count = sum(
            1
            for value in matches.values()
            if value
        )

        total_count = len(
            constraints
        )

        score = (
            matched_count / total_count
            if total_count
            else 0.0
        )

        return {
            "has_constraint": True,
            "matched": (
                matched_count
                == total_count
            ),
            "score": score,
            "matches": matches
        }

    # =========================================================
    # LEXICAL SCORE
    # =========================================================

    @classmethod
    def _lexical_score(
        cls,
        query: str,
        item: Dict[str, Any]
    ) -> float:

        query_tokens = cls._tokens(
            query
        )

        if not query_tokens:
            return 0.0

        content = item.get(
            "content",
            ""
        )

        metadata = cls._metadata(
            item
        )

        breadcrumbs = metadata.get(
            "breadcrumbs",
            ""
        )

        content_tokens = cls._tokens(
            content
        )

        breadcrumb_tokens = cls._tokens(
            breadcrumbs
        )

        content_overlap = (
            len(
                query_tokens
                & content_tokens
            )
            / len(query_tokens)
        )

        breadcrumb_overlap = (
            len(
                query_tokens
                & breadcrumb_tokens
            )
            / len(query_tokens)
        )

        return min(
            (
                content_overlap * 0.60
                +
                breadcrumb_overlap * 0.40
            ),
            1.0
        )

    # =========================================================
    # FINAL RERANK SCORE
    # =========================================================

    @classmethod
    def _rerank_score(
        cls,
        query: str,
        item: Dict[str, Any]
    ) -> float:

        semantic = float(
            item.get(
                "similarity",
                0.0
            )
        )

        semantic = max(
            0.0,
            min(
                semantic,
                1.0
            )
        )

        lexical = (
            cls._lexical_score(
                query,
                item
            )
        )

        hierarchy = (
            cls._hierarchy_match(
                query,
                item
            )
        )

        hierarchy_score = (
            hierarchy["score"]
        )

        # Base ranking.
        score = (
            semantic * 0.60
            +
            lexical * 0.20
            +
            hierarchy_score * 0.20
        )

        # Strong hierarchy protection.
        #
        # If the query explicitly specifies a hierarchy
        # such as Week 3 / Day 4, matching that hierarchy
        # is more important than a slightly higher semantic
        # similarity from another part of the document.

        if (
            hierarchy["has_constraint"]
            and hierarchy["matched"]
        ):

            score += 0.30

        elif (
            hierarchy["has_constraint"]
            and hierarchy_score > 0
        ):

            score += (
                hierarchy_score * 0.10
            )

        return min(
            score,
            1.0
        )

    # =========================================================
    # RERANK RESULTS
    # =========================================================

    @classmethod
    def _rerank(
        cls,
        query: str,
        results: List[
            Dict[str, Any]
        ],
        top_k: int
    ) -> List[
        Dict[str, Any]
    ]:

        if not results:
            return []

        hierarchy = (
            cls._extract_constraints(
                query
            )
        )

        for item in results:

            item["rerank_score"] = (
                cls._rerank_score(
                    query,
                    item
                )
            )

            item["_hierarchy"] = (
                cls._hierarchy_match(
                    query,
                    item
                )
            )

        # -----------------------------------------------------
        # If the question has explicit hierarchy,
        # matching hierarchy receives priority.
        # -----------------------------------------------------

        if hierarchy:

            results.sort(
                key=lambda item: (
                    item["_hierarchy"][
                        "matched"
                    ],
                    item["rerank_score"],
                    float(
                        item.get(
                            "similarity",
                            0.0
                        )
                    )
                ),
                reverse=True
            )

        else:

            results.sort(
                key=lambda item: (
                    item["rerank_score"],
                    float(
                        item.get(
                            "similarity",
                            0.0
                        )
                    )
                ),
                reverse=True
            )

        # Remove internal ranking data.
        for item in results:

            item.pop(
                "_hierarchy",
                None
            )

        return results[:top_k]

    # =========================================================
    # STORE CHUNKS
    # =========================================================

    def store_chunks(
        self,
        document_id: str,
        user_id: str,
        chunks: List[str],
        embeddings: List[
            List[float]
        ],
        metadatas: List[
            Dict[str, Any]
        ]
    ) -> bool:

        try:

            supabase = (
                self._get_supabase()
            )

            records = []

            for (
                chunk_text,
                emb,
                meta
            ) in zip(
                chunks,
                embeddings,
                metadatas
            ):

                records.append({

                    "document_id":
                        document_id,

                    "user_id":
                        user_id,

                    "content":
                        chunk_text,

                    "metadata":
                        meta,

                    "embedding":
                        emb
                })

            batch_size = 100

            for i in range(
                0,
                len(records),
                batch_size
            ):

                (
                    supabase
                    .table(
                        "document_chunks"
                    )
                    .insert(
                        records[
                            i:i + batch_size
                        ]
                    )
                    .execute()
                )

            logger.info(
                "Successfully stored %s "
                "chunks in Supabase.",
                len(chunks)
            )

        except Exception as exc:

            logger.warning(
                "Supabase storage failed: %s",
                exc
            )

        self._store_faiss(
            document_id,
            user_id,
            chunks,
            embeddings,
            metadatas
        )

        return True

    # =========================================================
    # SEARCH SIMILAR
    # =========================================================

    def search_similar(
        self,
        query_embedding: List[float],
        user_id: str,
        top_k: int = 8,
        threshold: float = 0.10,
        query_text: str = ""
    ) -> List[
        Dict[str, Any]
    ]:

        # Retrieve a larger candidate pool.
        candidate_k = max(
            top_k * 5,
            30
        )

        results = []

        try:

            supabase = (
                self._get_supabase()
            )

            response = (
                supabase
                .rpc(
                    "match_documents",
                    {
                        "query_embedding":
                            query_embedding,

                        "match_threshold":
                            threshold,

                        "match_count":
                            candidate_k,

                        "p_user_id":
                            user_id
                    }
                )
                .execute()
            )

            if response.data:

                results = list(
                    response.data
                )

                logger.info(
                    "Retrieved %s "
                    "Supabase candidates.",
                    len(results)
                )

        except Exception as exc:

            logger.warning(
                "Supabase vector search "
                "failed: %s",
                exc
            )

        # -----------------------------------------------------
        # FAISS fallback
        # -----------------------------------------------------

        if not results:

            results = (
                self._search_faiss(
                    query_embedding,
                    user_id,
                    candidate_k,
                    threshold
                )
            )

            logger.info(
                "Retrieved %s "
                "FAISS candidates.",
                len(results)
            )

        # -----------------------------------------------------
        # Reranking
        # -----------------------------------------------------

        if query_text:

            return self._rerank(
                query_text,
                results,
                top_k
            )

        results.sort(
            key=lambda item: float(
                item.get(
                    "similarity",
                    0.0
                )
            ),
            reverse=True
        )

        return results[:top_k]

    # =========================================================
    # FAISS STORE
    # =========================================================

    def _store_faiss(
        self,
        document_id: str,
        user_id: str,
        chunks: List[str],
        embeddings: List[
            List[float]
        ],
        metadatas: List[
            Dict[str, Any]
        ]
    ):

        embeddings_np = np.array(
            embeddings,
            dtype=np.float32
        )

        if (
            embeddings_np.ndim != 2
            or
            len(embeddings_np) == 0
        ):

            return

        faiss.normalize_L2(
            embeddings_np
        )

        if os.path.exists(
            self.faiss_file_path
        ):

            index = faiss.read_index(
                self.faiss_file_path
            )

            with open(
                self.meta_file_path,
                "r",
                encoding="utf-8"
            ) as f:

                metadata_store = (
                    json.load(f)
                )

        else:

            index = faiss.IndexFlatIP(
                self.dimension
            )

            metadata_store = []

        start_idx = len(
            metadata_store
        )

        index.add(
            embeddings_np
        )

        for i, (
            chunk_text,
            meta
        ) in enumerate(
            zip(
                chunks,
                metadatas
            )
        ):

            metadata_store.append({

                "faiss_id":
                    start_idx + i,

                "document_id":
                    document_id,

                "user_id":
                    user_id,

                "content":
                    chunk_text,

                "metadata":
                    meta
            })

        faiss.write_index(
            index,
            self.faiss_file_path
        )

        with open(
            self.meta_file_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                metadata_store,
                f,
                indent=2,
                ensure_ascii=False
            )

    # =========================================================
    # FAISS SEARCH
    # =========================================================

    def _search_faiss(
        self,
        query_embedding: List[float],
        user_id: str,
        top_k: int = 30,
        threshold: float = 0.10
    ) -> List[
        Dict[str, Any]
    ]:

        if (
            not os.path.exists(
                self.faiss_file_path
            )
            or
            not os.path.exists(
                self.meta_file_path
            )
        ):

            return []

        index = faiss.read_index(
            self.faiss_file_path
        )

        with open(
            self.meta_file_path,
            "r",
            encoding="utf-8"
        ) as f:

            metadata_store = (
                json.load(f)
            )

        if index.ntotal == 0:

            return []

        query_np = np.array(
            [query_embedding],
            dtype=np.float32
        )

        faiss.normalize_L2(
            query_np
        )

        search_k = min(
            max(
                top_k * 3,
                30
            ),
            index.ntotal
        )

        similarities, indices = (
            index.search(
                query_np,
                search_k
            )
        )

        results = []

        for (
            idx,
            similarity
        ) in zip(
            indices[0],
            similarities[0]
        ):

            if (
                idx < 0
                or
                idx >= len(
                    metadata_store
                )
            ):
                continue

            item = (
                metadata_store[idx]
            )

            if (
                item.get("user_id")
                != user_id
            ):
                continue

            similarity = float(
                similarity
            )

            if similarity < threshold:
                continue

            results.append({

                "id": str(
                    item.get(
                        "faiss_id"
                    )
                ),

                "document_id":
                    item.get(
                        "document_id"
                    ),

                "content":
                    item.get(
                        "content",
                        ""
                    ),

                "metadata":
                    item.get(
                        "metadata",
                        {}
                    ),

                "similarity":
                    similarity
            })

        return results


vector_store = VectorStoreManager()