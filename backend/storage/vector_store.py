import os
import json
import logging
import re
from typing import List, Dict, Any, Optional

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
    # TEXT NORMALIZATION
    # =========================================================

    @staticmethod
    def _normalize_text(
        text: Any
    ) -> str:

        return re.sub(
            r"[^a-z0-9\s]",
            " ",
            str(text).lower()
        ).strip()

    # =========================================================
    # WEEK / DAY EXTRACTION
    # =========================================================

    @staticmethod
    def _extract_week_day(
        query: str
    ):

        normalized = (
            VectorStoreManager
            ._normalize_text(query)
        )

        week_match = re.search(
            r"\bweek\s+(\d+)\b",
            normalized
        )

        day_match = re.search(
            r"\bday\s+(\d+)\b",
            normalized
        )

        week = (
            int(week_match.group(1))
            if week_match
            else None
        )

        day = (
            int(day_match.group(1))
            if day_match
            else None
        )

        return week, day

    # =========================================================
    # STRUCTURED METADATA MATCH
    # =========================================================

    @staticmethod
    def _get_item_metadata(
        item: Dict[str, Any]
    ) -> Dict[str, Any]:

        metadata = (
            item.get("metadata")
            or {}
        )

        if not isinstance(
            metadata,
            dict
        ):
            metadata = {}

        return metadata

    @classmethod
    def _structured_match(
        cls,
        query: str,
        item: Dict[str, Any]
    ) -> Dict[str, Any]:

        week, day = cls._extract_week_day(
            query
        )

        if week is None and day is None:

            return {
                "week_match": False,
                "day_match": False,
                "exact_match": False
            }

        metadata = cls._get_item_metadata(
            item
        )

        content = cls._normalize_text(
            item.get(
                "content",
                ""
            )
        )

        breadcrumbs = cls._normalize_text(
            metadata.get(
                "breadcrumbs",
                ""
            )
        )

        combined = (
            content
            + " "
            + breadcrumbs
        )

        metadata_week = metadata.get(
            "week"
        )

        metadata_day = metadata.get(
            "day"
        )

        # -----------------------------------------------------
        # Metadata is preferred.
        # -----------------------------------------------------

        week_match = False
        day_match = False

        if week is not None:

            if (
                metadata_week is not None
                and str(metadata_week) == str(week)
            ):

                week_match = True

            elif re.search(
                rf"\bweek\s+{week}\b",
                breadcrumbs,
                re.IGNORECASE
            ):

                week_match = True

            elif re.search(
                rf"\bweek\s+{week}\b",
                content,
                re.IGNORECASE
            ):

                week_match = True

        if day is not None:

            if (
                metadata_day is not None
                and str(metadata_day) == str(day)
            ):

                day_match = True

            elif re.search(
                rf"\bday\s+{day}\b",
                breadcrumbs,
                re.IGNORECASE
            ):

                day_match = True

            elif re.search(
                rf"\bday\s+{day}\b",
                content,
                re.IGNORECASE
            ):

                day_match = True

        exact_match = (
            (
                week is None
                or week_match
            )
            and
            (
                day is None
                or day_match
            )
        )

        return {
            "week_match": week_match,
            "day_match": day_match,
            "exact_match": exact_match
        }

    # =========================================================
    # HYBRID SCORE
    # =========================================================

    @classmethod
    def _hybrid_score(
        cls,
        query: str,
        item: Dict[str, Any]
    ) -> float:

        semantic_score = float(
            item.get(
                "similarity",
                0.0
            )
        )

        normalized_query = (
            cls._normalize_text(query)
        )

        metadata = cls._get_item_metadata(
            item
        )

        content = cls._normalize_text(
            item.get(
                "content",
                ""
            )
        )

        breadcrumbs = cls._normalize_text(
            metadata.get(
                "breadcrumbs",
                ""
            )
        )

        query_tokens = set(
            normalized_query.split()
        )

        content_tokens = set(
            content.split()
        )

        breadcrumb_tokens = set(
            breadcrumbs.split()
        )

        if query_tokens:

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

        else:

            content_overlap = 0.0
            breadcrumb_overlap = 0.0

        score = (
            semantic_score * 0.55
            + content_overlap * 0.20
            + breadcrumb_overlap * 0.25
        )

        # -----------------------------------------------------
        # Structured Week / Day matching
        # -----------------------------------------------------

        structured = (
            cls._structured_match(
                query,
                item
            )
        )

        week_match = structured[
            "week_match"
        ]

        day_match = structured[
            "day_match"
        ]

        exact_match = structured[
            "exact_match"
        ]

        # Strong boosts.
        if week_match:
            score += 0.20

        if day_match:
            score += 0.25

        if exact_match:
            score += 0.30

        return min(
            float(score),
            1.0
        )

    # =========================================================
    # RERANK
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

        week, day = (
            cls._extract_week_day(
                query
            )
        )

        structured_query = (
            week is not None
            or day is not None
        )

        exact_matches = []
        week_matches = []
        normal_matches = []

        for item in results:

            structured = (
                cls._structured_match(
                    query,
                    item
                )
            )

            item["hybrid_score"] = (
                cls._hybrid_score(
                    query,
                    item
                )
            )

            if (
                structured_query
                and structured[
                    "exact_match"
                ]
            ):

                exact_matches.append(
                    item
                )

            elif (
                structured_query
                and structured[
                    "week_match"
                ]
            ):

                week_matches.append(
                    item
                )

            else:

                normal_matches.append(
                    item
                )

        # -----------------------------------------------------
        # IMPORTANT:
        #
        # If exact Week + Day evidence exists,
        # do not allow another week's Day to outrank it.
        # -----------------------------------------------------

        if exact_matches:

            exact_matches.sort(
                key=lambda x:
                    x.get(
                        "hybrid_score",
                        0.0
                    ),
                reverse=True
            )

            return exact_matches[:top_k]

        # If Week matches exist, prefer them.
        if week_matches:

            week_matches.sort(
                key=lambda x:
                    x.get(
                        "hybrid_score",
                        0.0
                    ),
                reverse=True
            )

            normal_matches.sort(
                key=lambda x:
                    x.get(
                        "hybrid_score",
                        0.0
                    ),
                reverse=True
            )

            return (
                week_matches
                + normal_matches
            )[:top_k]

        # Normal semantic + lexical ranking.
        all_results = (
            normal_matches
        )

        all_results.sort(
            key=lambda x:
                x.get(
                    "hybrid_score",
                    0.0
                ),
            reverse=True
        )

        return all_results[:top_k]

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

                supabase.table(
                    "document_chunks"
                ).insert(
                    records[
                        i:i + batch_size
                    ]
                ).execute()

            logger.info(
                "Successfully stored %s "
                "chunks in Supabase pgvector.",
                len(chunks)
            )

        except Exception as e:

            logger.warning(
                "Supabase storage failed "
                "(%s). Continuing with "
                "local FAISS backup.",
                e
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

        # Retrieve a large candidate pool first.
        candidate_k = max(
            top_k * 6,
            40
        )

        try:

            supabase = (
                self._get_supabase()
            )

            response = (
                supabase.rpc(
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
                ).execute()
            )

            if response.data:

                results = list(
                    response.data
                )

                logger.info(
                    "Retrieved %s "
                    "candidate vectors "
                    "from Supabase.",
                    len(results)
                )

                if query_text:

                    return self._rerank(
                        query_text,
                        results,
                        top_k
                    )

                return results[:top_k]

        except Exception as e:

            logger.error(
                "Supabase pgvector query "
                "failed (%s). "
                "Using FAISS fallback.",
                e
            )

        results = self._search_faiss(
            query_embedding,
            user_id,
            candidate_k,
            threshold
        )

        if query_text:

            return self._rerank(
                query_text,
                results,
                top_k
            )

        return results[:top_k]

    # =========================================================
    # STORE FAISS
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
        top_k: int = 40,
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
            max(top_k * 2, 40),
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
                item.get(
                    "user_id"
                )
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
                        "content"
                    ),

                "metadata":
                    item.get(
                        "metadata"
                    ) or {},

                "similarity":
                    similarity
            })

        return results


vector_store = VectorStoreManager()