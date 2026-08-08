import asyncio
import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.auth.supabase_auth import (
    get_current_user
)
from backend.database.supabase_client import (
    supabase
)
from backend.rag.generator import (
    rag_generator
)
from backend.rag.srag_engine import (
    SRAGEngine
)
from backend.schemas.chat import (
    ChatRequest
)


router = APIRouter()

logger = logging.getLogger(__name__)

srag_engine = SRAGEngine(
    rag_generator
)


def _user_id(
    current_user: Any
) -> str:

    if hasattr(
        current_user,
        "id"
    ):
        return str(
            current_user.id
        )

    if (
        isinstance(
            current_user,
            dict
        )
        and current_user.get("id")
    ):
        return str(
            current_user["id"]
        )

    raise HTTPException(
        status_code=401,
        detail=(
            "Could not resolve "
            "user identity."
        )
    )


def _load_conversation(
    session_id: str,
    user_id: str,
    limit: int = 8
) -> List[Dict[str, str]]:

    if not session_id:
        return []

    response = (
        supabase
        .table("chat_messages")
        .select(
            "role, content, created_at"
        )
        .eq(
            "session_id",
            session_id
        )
        .eq(
            "user_id",
            user_id
        )
        .order(
            "created_at",
            desc=True
        )
        .limit(limit)
        .execute()
    )

    rows = list(
        reversed(
            response.data or []
        )
    )

    return [
        {
            "role": str(
                row.get(
                    "role",
                    "user"
                )
            ),
            "content": str(
                row.get(
                    "content",
                    ""
                )
            )
        }

        for row in rows

        if row.get("content")
    ]


def _chunk_text(
    text: str,
    size: int = 80
):

    """
    Streams an already validated answer.

    SRAG intentionally validates the complete answer
    before the frontend receives it.
    """

    text = text or ""

    for start in range(
        0,
        len(text),
        size
    ):

        yield text[
            start:start + size
        ]


@router.post("/query")
async def chat_query(
    request: ChatRequest,
    current_user: dict = Depends(
        get_current_user
    )
):

    query_text = (
        request.query.strip()
    )

    if not query_text:

        raise HTTPException(
            status_code=400,
            detail=(
                "Query cannot be empty."
            )
        )

    user_id = _user_id(
        current_user
    )

    session_id = (
        request.session_id
    )

    title = None

    is_new_session = False

    # =========================================================
    # SESSION
    # =========================================================

    if session_id:

        # IMPORTANT:
        # Verify the session belongs to this user.
        session_check = (
            supabase
            .table("chat_sessions")
            .select("id")
            .eq(
                "id",
                session_id
            )
            .eq(
                "user_id",
                user_id
            )
            .limit(1)
            .execute()
        )

        if not session_check.data:

            raise HTTPException(
                status_code=404,
                detail=(
                    "Chat session not found."
                )
            )

    else:

        is_new_session = True

        title = (
            rag_generator
            .generate_chat_title(
                query_text
            )
        )

        session_res = (
            supabase
            .table("chat_sessions")
            .insert(
                {
                    "user_id": user_id,
                    "title": title
                }
            )
            .execute()
        )

        if not session_res.data:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Failed to create "
                    "chat session."
                )
            )

        session_id = (
            session_res
            .data[0]["id"]
        )

    # =========================================================
    # CONVERSATION HISTORY
    # =========================================================

    conversation = (
        _load_conversation(
            session_id,
            user_id,
            limit=8
        )
    )

    # =========================================================
    # SAVE USER MESSAGE
    # =========================================================

    (
        supabase
        .table("chat_messages")
        .insert(
            {
                "session_id": session_id,
                "user_id": user_id,
                "role": "user",
                "content": query_text
            }
        )
        .execute()
    )

    # =========================================================
    # SRAG STREAM
    # =========================================================

    async def stream_generator():

        try:

            # Run the SRAG pipeline off the async event loop.
            #
            # This allows the FastAPI server to continue
            # handling other requests while the LLM/retrieval
            # pipeline runs.

            result = await asyncio.to_thread(

                srag_engine.answer,

                query_text,

                user_id,

                conversation
            )

            # -------------------------------------------------
            # META EVENT
            # -------------------------------------------------

            meta_payload = {

                "type": "meta",

                "session_id": session_id,

                "title": title,

                "is_new_session":
                    is_new_session,

                "sources":
                    result.sources,

                "srag": {

                    "status":
                        result.status,

                    "retrieval_attempts":
                        result.retrieval_attempts,

                    "rewrite_attempts":
                        result.rewrite_attempts,

                    "support_revisions":
                        result.support_revisions,

                    "retrieval_query":
                        result.retrieval_query
                }
            }

            yield (
                "data: "
                f"{json.dumps(meta_payload)}"
                "\n\n"
            )

            # -------------------------------------------------
            # FINAL VALIDATED ANSWER
            # -------------------------------------------------

            full_response = (
                result.answer
            )

            for chunk in _chunk_text(
                full_response
            ):

                yield (
                    "data: "
                    f"{json.dumps({
                        'type': 'token',
                        'content': chunk,
                        'session_id': session_id
                    })}"
                    "\n\n"
                )

                await asyncio.sleep(
                    0.005
                )

            # -------------------------------------------------
            # SAVE ASSISTANT RESPONSE
            # -------------------------------------------------

            (
                supabase
                .table("chat_messages")
                .insert(
                    {
                        "session_id":
                            session_id,

                        "user_id":
                            user_id,

                        "role":
                            "assistant",

                        "content":
                            full_response,

                        "sources":
                            result.sources
                    }
                )
                .execute()
            )

            (
                supabase
                .table("chat_sessions")
                .update(
                    {
                        "updated_at":
                            "now()"
                    }
                )
                .eq(
                    "id",
                    session_id
                )
                .eq(
                    "user_id",
                    user_id
                )
                .execute()
            )

        except Exception as err:

            logger.exception(
                "SRAG chat request failed"
            )

            error_text = (
                "An error occurred while "
                "processing your question. "
                "Please try again."
            )

            yield (
                "data: "
                f"{json.dumps({
                    'type': 'token',
                    'content': error_text,
                    'session_id': session_id
                })}"
                "\n\n"
            )

        finally:

            yield (
                "data: [DONE]\n\n"
            )

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream"
    )