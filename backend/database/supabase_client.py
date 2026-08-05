from supabase import create_client, Client
from backend.core.config import settings
import logging

logger = logging.getLogger(__name__)

def get_supabase_client() -> Client:
    try:
        supabase: Client = create_client(
            settings.SUPABASE_URL, 
            settings.SUPABASE_SERVICE_KEY
        )
        return supabase
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {str(e)}")
        raise e