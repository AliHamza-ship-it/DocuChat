from pydantic import BaseModel
from typing import List, Dict, Any

class ChatRequest(BaseModel):
    query: str
    
class Citation(BaseModel):
    document_id: str
    content: str
    metadata: Dict[str, Any]
    similarity: float

class ChatResponse(BaseModel):
    answer: str
    sources: List[Citation]