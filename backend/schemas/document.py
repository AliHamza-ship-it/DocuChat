from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class DocumentResponse(BaseModel):
    id: str
    filename: str
    created_at: datetime

class UploadResponse(BaseModel):
    message: str
    document_id: str
    chunks_processed: int