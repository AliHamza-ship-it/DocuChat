from sentence_transformers import SentenceTransformer
from backend.core.config import settings
import logging

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        logger.info(f"Loading local embedding model: {settings.EMBEDDING_MODEL}")
        self.model = SentenceTransformer(settings.EMBEDDING_MODEL)
        
    def generate_embedding(self, text: str) -> list[float]:
        """Generates a normalized 384-dimensional vector array for a given text."""
        clean_text = text.replace("\n", " ").strip()
        # Enforce L2 normalization for accurate cosine similarity
        vector = self.model.encode(clean_text, normalize_embeddings=True)
        return vector.tolist()
        
    def generate_batch_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Optimized batch generation for document chunks."""
        clean_texts = [text.replace("\n", " ").strip() for text in texts]
        vectors = self.model.encode(clean_texts, normalize_embeddings=True)
        return vectors.tolist()

embedding_service = EmbeddingService()