import os

from pydantic_settings import (
    BaseSettings
)

from dotenv import load_dotenv


load_dotenv()


class Settings(BaseSettings):

    PROJECT_NAME: str = "DocuChat API"

    VERSION: str = "1.0.0"

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

    EMBEDDING_MODEL: str = (
        "all-MiniLM-L6-v2"
    )

    EMBEDDING_DIMENSIONS: int = 384

    # =========================================================
    # SRAG
    # =========================================================

    SRAG_MAX_RETRIEVAL_ATTEMPTS: int = 5

    SRAG_MAX_REWRITE_ATTEMPTS: int = 5

    SRAG_MAX_SUPPORT_REVISIONS: int = 3

    SRAG_RETRIEVAL_CANDIDATES: int = 20

    SRAG_CONTEXT_CHUNKS: int = 6

    SRAG_MIN_SIMILARITY: float = 0.10


settings = Settings()