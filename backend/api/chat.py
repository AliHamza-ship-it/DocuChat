import json
import asyncio
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from backend.auth.supabase_auth import get_current_user
from backend.schemas.chat import ChatRequest
from backend.embeddings.vectorizer import embedding_service
from backend.storage.vector_store import vector_store
from backend.rag.generator import rag_generator

router = APIRouter()

@router.post("/query")
async def chat_query(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    query_text = request.query.strip()
    
    # 1. Vectorize query
    query_embedding = embedding_service.generate_embedding(query_text)
    
    # 2. Retrieve top-k context vectors
    # OPTIMIZED THRESHOLD: 0.35 catches valid topics without grabbing random trash
    retrieved_chunks = vector_store.search_similar(
        query_embedding=query_embedding,
        user_id=current_user.id,
        top_k=5,
        threshold=0.35 
    )
    
    # 3. Structure sources payload
    sources = [
        {
            "document_id": str(c.get("document_id", "")),
            "content": c.get("content", ""),
            "metadata": c.get("metadata", {}),
            "similarity": float(c.get("similarity", 0.0))
        }
        for c in retrieved_chunks
    ]
    
    # 4. Stream generator pushing SSE events
    async def stream_generator():
        # First send context citations
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        
        # Check if RAG generator supports streaming generator or single answer
        if hasattr(rag_generator, "stream_grounded_answer"):
            stream = rag_generator.stream_grounded_answer(query_text, retrieved_chunks)
        else:
            stream = rag_generator.generate_grounded_answer(query_text, retrieved_chunks)

        # Handle async generator, iterator, or single string output
        if hasattr(stream, "__aiter__"):
            async for chunk in stream:
                yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
        elif hasattr(stream, "__iter__") and not isinstance(stream, str):
            for chunk in stream:
                yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
                await asyncio.sleep(0.02) # Adds a slight delay to make word-by-word streaming visible
        else:
            yield f"data: {json.dumps({'type': 'token', 'content': str(stream)})}\n\n"
            
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")