import json
import asyncio

from fastapi import (
    APIRouter,
    Depends
)

from fastapi.responses import (
    StreamingResponse
)

from backend.auth.supabase_auth import (
    get_current_user
)

from backend.schemas.chat import (
    ChatRequest
)

from backend.rag.generator import (
    rag_generator
)

from backend.rag.srag import (
    SRAGEngine
)

from backend.database.supabase_client import (
    supabase
)


router = APIRouter()


srag_engine = SRAGEngine(
    rag_generator
)


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

    user_id = current_user.id

    session_id = getattr(
        request,
        "session_id",
        None
    )

    is_new_session = False

    title = None

    if not session_id:

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
            .insert({
                "user_id":
                    user_id,
                "title":
                    title
            })
            .execute()
        )

        session_id = (
            session_res
            .data[0]["id"]
        )

    # =========================================================
    # LOAD PREVIOUS CONVERSATION BEFORE SAVING THIS QUESTION
    # =========================================================
    # This is required for contextual follow-ups such as:
    #   Q1: What is in Week 5 Day 2?
    #   Q2: What is after that?
    # The current question must NOT be included in the history
    # passed to SRAG.
    # =========================================================

    conversation = []

    if session_id:
        try:
            history_res = (
                supabase
                .table("chat_messages")
                .select("*")
                .eq("session_id", session_id)
                .eq("user_id", user_id)
                .limit(20)
                .execute()
            )

            history_rows = list(
                history_res.data or []
            )

            # If the table exposes created_at, use it for deterministic
            # chronological ordering. Otherwise preserve the database
            # response order.
            if any(
                row.get("created_at")
                for row in history_rows
                if isinstance(row, dict)
            ):
                history_rows.sort(
                    key=lambda row: str(
                        row.get("created_at", "")
                    )
                )

            for row in history_rows:
                if not isinstance(row, dict):
                    continue

                role = str(
                    row.get("role", "")
                ).strip().lower()

                content = str(
                    row.get("content", "")
                ).strip()

                if role in {"user", "assistant"} and content:
                    conversation.append({
                        "role": role,
                        "content": content
                    })

            # Keep only the most recent turns so context remains bounded.
            conversation = conversation[-12:]

        except Exception as history_error:
            # Do not break normal direct questions if history loading fails.
            # Contextual follow-ups will simply have no history to resolve.
            conversation = []

    # =========================================================
    # SAVE CURRENT USER MESSAGE
    # =========================================================

    supabase.table(
        "chat_messages"
    ).insert({

        "session_id":
            session_id,

        "user_id":
            user_id,

        "role":
            "user",

        "content":
            query_text

    }).execute()

    async def stream_generator():

        try:

            result = await asyncio.to_thread(
                srag_engine.answer,
                query_text,
                user_id,
                conversation
            )

            sources = (
                result.sources
            )

            yield (
                "data: "
                +
                json.dumps({
                    "type":
                        "meta",

                    "session_id":
                        session_id,

                    "title":
                        title,

                    "is_new_session":
                        is_new_session,

                    "sources":
                        sources,

                    "retrieval_query":
                        result.retrieval_query,

                    "retrieval_attempts":
                        result.retrieval_attempts,

                    "rewrite_attempts":
                        result.rewrite_attempts,

                    "status":
                        result.status

                })
                +
                "\n\n"
            )

            answer = (
                result.answer
            )

            # Stream the already validated
            # final answer to the frontend.
            for i in range(
                0,
                len(answer),
                40
            ):

                piece = answer[
                    i:i + 40
                ]

                yield (
                    "data: "
                    +
                    json.dumps({
                        "type":
                            "token",

                        "content":
                            piece,

                        "session_id":
                            session_id
                    })
                    +
                    "\n\n"
                )

                await asyncio.sleep(
                    0.005
                )

            supabase.table(
                "chat_messages"
            ).insert({

                "session_id":
                    session_id,

                "user_id":
                    user_id,

                "role":
                    "assistant",

                "content":
                    answer,

                "sources":
                    sources

            }).execute()

            supabase.table(
                "chat_sessions"
            ).update({
                "updated_at":
                    "now()"
            }).eq(
                "id",
                session_id
            ).execute()

        except Exception as err:

            error_text = (
                "An error occurred: "
                f"{str(err)}"
            )

            yield (
                "data: "
                +
                json.dumps({
                    "type":
                        "token",

                    "content":
                        error_text,

                    "session_id":
                        session_id
                })
                +
                "\n\n"
            )

        finally:

            yield (
                "data: [DONE]\n\n"
            )

    return StreamingResponse(
        stream_generator(),
        media_type=
            "text/event-stream"
    )