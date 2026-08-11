from sentence_transformers import SentenceTransformer

from backend.core.config import settings

import logging

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        logger.info(
            "Loading local embedding model: %s",
            settings.EMBEDDING_MODEL,
        )

        self.model = SentenceTransformer(
            settings.EMBEDDING_MODEL
        )

    @staticmethod
    def _clean(text: str) -> str:
        return (
            str(text or "")
            .replace("\n", " ")
            .strip()
        )

    def generate_embedding(
        self,
        text: str,
    ) -> list[float]:
        """Generate one normalized embedding."""
        clean_text = self._clean(text)

        if not clean_text:
            raise ValueError(
                "Cannot generate an embedding for empty text."
            )

        vector = self.model.encode(
            clean_text,
            normalize_embeddings=True,
        )

        return vector.tolist()

    def generate_batch_embeddings(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """
        Generate normalized embeddings in a bounded model batch.

        The returned order is identical to the input order.
        """
        clean_texts = [
            self._clean(text)
            for text in texts
        ]

        if not clean_texts:
            return []

        if any(
            not text
            for text in clean_texts
        ):
            raise ValueError(
                "Cannot generate embeddings for empty chunks."
            )

        vectors = self.model.encode(
            clean_texts,
            batch_size=64,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        result = vectors.tolist()

        if len(result) != len(clean_texts):
            raise RuntimeError(
                "Embedding count does not match chunk count."
            )

        return result


embedding_service = EmbeddingService()