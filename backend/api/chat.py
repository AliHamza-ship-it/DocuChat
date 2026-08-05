from fastapi import APIRouter, Depends
from backend.auth.supabase_auth import get_current_user
from backend.schemas.chat import ChatRequest, ChatResponse, Citation
from backend.embeddings.vectorizer import embedding_service
from backend.storage.vector_store import vector_store
from backend.rag.generator import rag_generator

router = APIRouter()

@router.post("/query", response_model=ChatResponse)
def chat_query(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    query_text = request.query.strip()
    
    # 1. Vectorize query
    query_embedding = embedding_service.generate_embedding(query_text)
    
    # 2. Retrieve top-k context vectors
    retrieved_chunks = vector_store.search_similar(
        query_embedding=query_embedding,
        user_id=current_user.id,
        top_k=5,
        threshold=0.25
    )
    
    # 3. Generate grounded answer
    answer = rag_generator.generate_grounded_answer(query_text, retrieved_chunks)
    
    # 4. Structure sources for citation display on frontend
    sources = [
        Citation(
            document_id=str(c.get("document_id", "")),
            content=c.get("content", ""),
            metadata=c.get("metadata", {}),
            similarity=float(c.get("similarity", 0.0))
        )
        for c in retrieved_chunks
    ]
    
    return ChatResponse(
        answer=answer,
        sources=sources
    )