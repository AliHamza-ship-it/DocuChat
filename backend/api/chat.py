import json
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from backend.auth.supabase_auth import get_current_user
from backend.schemas.chat import ChatRequest
from backend.embeddings.vectorizer import embedding_service
from backend.storage.vector_store import vector_store
from backend.rag.generator import rag_generator
from backend.database.supabase_client import supabase

router = APIRouter()

@router.post("/query")
async def chat_query(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    query_text = request.query.strip()
    session_id = getattr(request, 'session_id', None)
    user_id = current_user.id

    is_new_session = False
    if not session_id:
        is_new_session = True
        title = rag_generator.generate_chat_title(query_text)
        session_res = supabase.table("chat_sessions").insert({
            "user_id": user_id,
            "title": title
        }).execute()
        
        session_id = session_res.data[0]["id"]
    else:
        title = None

    supabase.table("chat_messages").insert({
        "session_id": session_id,
        "user_id": user_id,
        "role": "user",
        "content": query_text
    }).execute()

    query_embedding = embedding_service.generate_embedding(query_text)
    retrieved_chunks = vector_store.search_similar(
        query_embedding=query_embedding,
        user_id=user_id,
        top_k=5,
        threshold=0.35
    )

    sources = [
        {
            "document_id": str(c.get("document_id", "")),
            "content": c.get("content", ""),
            "metadata": c.get("metadata", {}),
            "similarity": float(c.get("similarity", 0.0))
        }
        for c in retrieved_chunks
    ]

    async def stream_generator():
        meta_payload = {
            'type': 'meta',
            'session_id': session_id,
            'title': title,
            'is_new_session': is_new_session,
            'sources': sources
        }
        yield f"data: {json.dumps(meta_payload)}\n\n"

        full_assistant_response = []

        if hasattr(rag_generator, "stream_grounded_answer"):
            stream = rag_generator.stream_grounded_answer(query_text, retrieved_chunks)
        else:
            stream = rag_generator.generate_grounded_answer(query_text, retrieved_chunks)

        if hasattr(stream, "__aiter__"):
            async for chunk in stream:
                if chunk:
                    full_assistant_response.append(chunk)
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk, 'session_id': session_id})}\n\n"
        elif hasattr(stream, "__iter__") and not isinstance(stream, str):
            for chunk in stream:
                if chunk:
                    full_assistant_response.append(chunk)
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk, 'session_id': session_id})}\n\n"
                    await asyncio.sleep(0.005)
        else:
            chunk = str(stream)
            full_assistant_response.append(chunk)
            yield f"data: {json.dumps({'type': 'token', 'content': chunk, 'session_id': session_id})}\n\n"

        complete_text = "".join(full_assistant_response)
        supabase.table("chat_messages").insert({
            "session_id": session_id,
            "user_id": user_id,
            "role": "assistant",
            "content": complete_text,
            "sources": sources
        }).execute()

        supabase.table("chat_sessions").update({"updated_at": "now()"}).eq("id", session_id).execute()

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")