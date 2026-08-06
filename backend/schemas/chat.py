from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None  # Allow the frontend to send the session ID
    
class Citation(BaseModel):
    document_id: str
    content: str
    metadata: Dict[str, Any]
    similarity: float

class ChatResponse(BaseModel):
    answer: str
    sources: List[Citation]