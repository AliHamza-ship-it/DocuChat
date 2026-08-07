import os
import json
import logging
import numpy as np
import faiss
from typing import List, Dict, Any
from supabase import Client
from backend.database.supabase_client import get_supabase_client
from backend.core.config import settings

logger = logging.getLogger(__name__)

class VectorStoreManager:
    def __init__(self):
        self.dimension = settings.EMBEDDING_DIMENSIONS
        self.faiss_dir = os.path.join(os.path.dirname(__file__), "..", "faiss_index")
        os.makedirs(self.faiss_dir, exist_ok=True)
        self.faiss_file_path = os.path.join(self.faiss_dir, "index.faiss")
        self.meta_file_path = os.path.join(self.faiss_dir, "metadata.json")

    def _get_supabase(self) -> Client:
        return get_supabase_client()

    def store_chunks(
        self,
        document_id: str,
        user_id: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]]
    ) -> bool:
        """Stores chunk embeddings into Supabase pgvector with local FAISS backup."""
        try:
            supabase = self._get_supabase()
            records = []
            for chunk_text, emb, meta in zip(chunks, embeddings, metadatas):
                records.append({
                    "document_id": document_id,
                    "user_id": user_id,
                    "content": chunk_text,
                    "metadata": meta,
                    "embedding": emb
                })
            
            batch_size = 100
            for i in range(0, len(records), batch_size):
                supabase.table("document_chunks").insert(records[i:i + batch_size]).execute()
            logger.info(f"Successfully stored {len(chunks)} chunks in Supabase pgvector.")
        except Exception as e:
            logger.warning(f"Supabase storage failed ({str(e)}). Falling back to FAISS backup index.")

        self._store_faiss(document_id, user_id, chunks, embeddings, metadatas)
        return True

    def search_similar(
        self,
        query_embedding: List[float],
        user_id: str,
        top_k: int = 8,
        threshold: float = 0.15
    ) -> List[Dict[str, Any]]:
        """Performs vector search in Supabase; falls back to FAISS if primary search fails."""
        try:
            supabase = self._get_supabase()
            response = supabase.rpc("match_documents", {
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": top_k,
                "p_user_id": user_id
            }).execute()

            if response.data:
                logger.info("Retrieved context vectors from Supabase pgvector.")
                return response.data
        except Exception as e:
            logger.error(f"Supabase pgvector query failed ({str(e)}). Executing local FAISS fallback.")

        return self._search_faiss(query_embedding, user_id, top_k, threshold)

    def _store_faiss(
        self,
        document_id: str,
        user_id: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]]
    ):
        """Indexes vector chunks into a local FAISS index file."""
        embeddings_np = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(embeddings_np)

        if os.path.exists(self.faiss_file_path):
            index = faiss.read_index(self.faiss_file_path)
            with open(self.meta_file_path, "r") as f:
                metadata_store = json.load(f)
        else:
            index = faiss.IndexFlatIP(self.dimension)
            metadata_store = []

        start_idx = len(metadata_store)
        index.add(embeddings_np)

        for i, (chunk_text, meta) in enumerate(zip(chunks, metadatas)):
            metadata_store.append({
                "faiss_id": start_idx + i,
                "document_id": document_id,
                "user_id": user_id,
                "content": chunk_text,
                "metadata": meta
            })

        faiss.write_index(index, self.faiss_file_path)
        with open(self.meta_file_path, "w") as f:
            json.dump(metadata_store, f, indent=2)

    def _search_faiss(
        self,
        query_embedding: List[float],
        user_id: str,
        top_k: int = 8,
        threshold: float = 0.15
    ) -> List[Dict[str, Any]]:
        """Searches vector embeddings in local FAISS index."""
        if not os.path.exists(self.faiss_file_path) or not os.path.exists(self.meta_file_path):
            return []

        index = faiss.read_index(self.faiss_file_path)
        with open(self.meta_file_path, "r") as f:
            metadata_store = json.load(f)

        query_np = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(query_np)

        similarities, indices = index.search(query_np, top_k * 3)

        results = []
        for idx, similarity in zip(indices[0], similarities[0]):
            if idx < 0 or idx >= len(metadata_store):
                continue
            item = metadata_store[idx]
            if item.get("user_id") == user_id and float(similarity) >= threshold:
                results.append({
                    "id": str(item.get("faiss_id")),
                    "document_id": item.get("document_id"),
                    "content": item.get("content"),
                    "metadata": item.get("metadata"),
                    "similarity": float(similarity)
                })
                if len(results) >= top_k:
                    break

        return results

vector_store = VectorStoreManager()