from fastapi import APIRouter, Depends, HTTPException
from backend.auth.supabase_auth import get_current_user
from backend.database.supabase_client import supabase

router = APIRouter()

@router.get("/sessions")
async def get_sessions(current_user: dict = Depends(get_current_user)):
    """Fetch all chat sessions for the logged-in user."""
    res = supabase.table("chat_sessions") \
        .select("id, title, created_at, updated_at") \
        .eq("user_id", current_user.id) \
        .order("updated_at", desc=True) \
        .execute()
    return res.data

@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, current_user: dict = Depends(get_current_user)):
    """Fetch all messages for a specific session."""
    res = supabase.table("chat_messages") \
        .select("id, role, content, sources, created_at") \
        .eq("session_id", session_id) \
        .eq("user_id", current_user.id) \
        .order("created_at", desc=False) \
        .execute()
    return res.data

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a chat session."""
    supabase.table("chat_sessions").delete().eq("id", session_id).eq("user_id", current_user.id).execute()
    return {"status": "deleted"}