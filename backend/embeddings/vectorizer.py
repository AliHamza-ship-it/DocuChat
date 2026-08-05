from sentence_transformers import SentenceTransformer
from backend.core.config import settings
import logging

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        logger.info(f"Loading local embedding model: {settings.EMBEDDING_MODEL}")
        # Loads all-MiniLM-L6-v2 locally (free and highly effective for RAG)
        self.model = SentenceTransformer(settings.EMBEDDING_MODEL)
        
    def generate_embedding(self, text: str) -> list[float]:
        """Generates a 384-dimensional vector array for a given text."""
        # Clean text slightly before embedding
        clean_text = text.replace("\n", " ").strip()
        vector = self.model.encode(clean_text)
        return vector.tolist()
        
    def generate_batch_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Optimized batch generation for document chunks."""
        clean_texts = [text.replace("\n", " ").strip() for text in texts]
        vectors = self.model.encode(clean_texts)
        return vectors.tolist()

# Singleton instance to prevent reloading the ML model into RAM on every request
embedding_service = EmbeddingService()