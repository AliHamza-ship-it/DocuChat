import os

from pydantic_settings import BaseSettings
from dotenv import load_dotenv


load_dotenv()


class Settings(BaseSettings):

    PROJECT_NAME: str = "DocuChat API"

    VERSION: str = "2.0.0"

    SUPABASE_URL: str = os.getenv(
        "SUPABASE_URL",
        ""
    )

    SUPABASE_SERVICE_KEY: str = os.getenv(
        "SUPABASE_SERVICE_KEY",
        ""
    )

    OPENROUTER_API_KEY: str = os.getenv(
        "OPENROUTER_API_KEY",
        ""
    )

    # ---------------------------------------------------------
    # Embeddings
    # ---------------------------------------------------------

    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    EMBEDDING_DIMENSIONS: int = 384

    # ---------------------------------------------------------
    # SRAG
    # ---------------------------------------------------------

    # Maximum number of retrieval cycles.
    SRAG_MAX_RETRIEVAL_ATTEMPTS: int = int(
        os.getenv(
            "SRAG_MAX_RETRIEVAL_ATTEMPTS",
            "4"
        )
    )

    # Maximum times an answer may be revised
    # against the same evidence.
    SRAG_MAX_SUPPORT_REVISIONS: int = int(
        os.getenv(
            "SRAG_MAX_SUPPORT_REVISIONS",
            "3"
        )
    )

    # Maximum query rewrites.
    SRAG_MAX_REWRITE_ATTEMPTS: int = int(
        os.getenv(
            "SRAG_MAX_REWRITE_ATTEMPTS",
            "3"
        )
    )

    # First-stage retrieval candidates.
    SRAG_RETRIEVAL_CANDIDATES: int = int(
        os.getenv(
            "SRAG_RETRIEVAL_CANDIDATES",
            "12"
        )
    )

    # Number of validated chunks finally passed to generation.
    SRAG_CONTEXT_CHUNKS: int = int(
        os.getenv(
            "SRAG_CONTEXT_CHUNKS",
            "6"
        )
    )

    # Initial semantic similarity gate.
    SRAG_MIN_SIMILARITY: float = float(
        os.getenv(
            "SRAG_MIN_SIMILARITY",
            "0.20"
        )
    )


settings = Settings()