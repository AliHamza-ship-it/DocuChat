from typing import Any, List

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
)

from backend.auth.supabase_auth import get_current_user
from backend.rag.parser import parse_pdf, parse_docx
from backend.rag.chunker import process_document_to_chunks
from backend.database.supabase_client import get_supabase_client
from backend.embeddings.vectorizer import embedding_service
from backend.storage.vector_store import vector_store
from backend.schemas.document import (
    UploadResponse,
    DocumentResponse,
)

import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_user_id(user: Any) -> str:
    """Safely extract the authenticated user's ID."""
    if hasattr(user, "id"):
        return str(user.id)

    if isinstance(user, dict) and "id" in user:
        return str(user["id"])

    raise HTTPException(
        status_code=401,
        detail="Could not resolve user identity.",
    )


@router.post(
    "/upload",
    response_model=UploadResponse,
)
async def upload_document(
    file: UploadFile = File(...),
    current_user: Any = Depends(get_current_user),
):
    filename = (
        file.filename
        or "uploaded_document"
    )

    ext = (
        filename.rsplit(".", 1)[-1].lower()
        if "." in filename
        else ""
    )

    if ext not in {"pdf", "docx"}:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. "
                "Only PDF and DOCX files are allowed."
            ),
        )

    user_id = get_user_id(
        current_user
    )

    try:
        content_bytes = await file.read()

        if not content_bytes:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        # -----------------------------------------------------
        # 1. EXTRACT THE COMPLETE DOCUMENT
        # -----------------------------------------------------
        if ext == "pdf":
            parsed_pages = parse_pdf(
                content_bytes,
                filename,
            )
        else:
            parsed_pages = parse_docx(
                content_bytes,
                filename,
            )

        if not parsed_pages:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Failed to extract text "
                    "from document."
                ),
            )

        # -----------------------------------------------------
        # 2. CHUNK THE COMPLETE EXTRACTED CONTENT
        # -----------------------------------------------------
        chunks_data = process_document_to_chunks(
            parsed_pages
        )

        if not chunks_data:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Document contains no "
                    "indexable content."
                ),
            )

        texts_to_embed = [
            str(chunk["content"]).strip()
            for chunk in chunks_data
        ]

        metadatas = [
            chunk["metadata"]
            for chunk in chunks_data
        ]

        if any(
            not text
            for text in texts_to_embed
        ):
            raise HTTPException(
                status_code=500,
                detail=(
                    "Chunking produced an empty "
                    "chunk. Document was not indexed."
                ),
            )

        logger.info(
            "Document '%s': extracted_pages=%s, "
            "chunks=%s, user_id=%s",
            filename,
            len(parsed_pages),
            len(chunks_data),
            user_id,
        )

        # -----------------------------------------------------
        # 3. EMBED EVERY CHUNK
        #
        # Do this before creating the DB document record so an
        # embedding failure cannot leave an orphan document row.
        # -----------------------------------------------------
        embeddings = (
            embedding_service
            .generate_batch_embeddings(
                texts_to_embed
            )
        )

        if len(embeddings) != len(chunks_data):
            raise HTTPException(
                status_code=500,
                detail=(
                    "Embedding count does not match "
                    "chunk count. Document was not indexed."
                ),
            )

        # -----------------------------------------------------
        # 4. CREATE DOCUMENT RECORD
        # -----------------------------------------------------
        supabase = get_supabase_client()

        doc_res = (
            supabase
            .table("documents")
            .insert({
                "filename": filename,
                "user_id": user_id,
            })
            .execute()
        )

        if not doc_res.data:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Failed to register "
                    "document record."
                ),
            )

        document_id = doc_res.data[0]["id"]

        # -----------------------------------------------------
        # 5. STORE THE COMPLETE INDEX
        # -----------------------------------------------------
        try:
            stored_count = (
                vector_store.store_chunks(
                    document_id=document_id,
                    user_id=user_id,
                    chunks=texts_to_embed,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
            )

        except Exception as exc:
            logger.exception(
                "Indexing failed for document %s.",
                document_id,
            )

            # Remove the document row created for this failed
            # indexing operation. document_chunks cleanup is
            # already attempted inside store_chunks.
            try:
                (
                    supabase
                    .table("documents")
                    .delete()
                    .eq("id", document_id)
                    .eq("user_id", user_id)
                    .execute()
                )
            except Exception:
                logger.exception(
                    "Failed to remove orphan document %s.",
                    document_id,
                )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Document extraction/chunking succeeded, "
                    "but indexing failed. No partial document "
                    "was reported as successfully uploaded."
                ),
            ) from exc

        if stored_count != len(chunks_data):
            # Defensive check. store_chunks is expected to raise
            # before this point on a mismatch.
            try:
                (
                    supabase
                    .table("document_chunks")
                    .delete()
                    .eq("document_id", document_id)
                    .eq("user_id", user_id)
                    .execute()
                )

                (
                    supabase
                    .table("documents")
                    .delete()
                    .eq("id", document_id)
                    .eq("user_id", user_id)
                    .execute()
                )
            except Exception:
                logger.exception(
                    "Failed cleanup after chunk count mismatch "
                    "for document %s.",
                    document_id,
                )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Only part of the document was indexed. "
                    "The upload was rejected."
                ),
            )

        logger.info(
            "Document %s indexed successfully: %s chunks.",
            document_id,
            stored_count,
        )

        return UploadResponse(
            message=(
                "Document uploaded, chunked, "
                "and indexed successfully."
            ),
            document_id=document_id,
            chunks_processed=stored_count,
        )

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception(
            "Unexpected document upload failure for %s.",
            filename,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to process the document. "
                "Please try uploading it again."
            ),
        ) from exc


@router.get(
    "/list",
    response_model=List[DocumentResponse],
)
def list_documents(
    current_user: Any = Depends(
        get_current_user
    ),
):
    user_id = get_user_id(
        current_user
    )

    supabase = get_supabase_client()

    res = (
        supabase
        .table("documents")
        .select("*")
        .eq("user_id", user_id)
        .order(
            "created_at",
            desc=True,
        )
        .execute()
    )

    return res.data or []


@router.delete(
    "/{document_id}",
)
def delete_document(
    document_id: str,
    current_user: Any = Depends(
        get_current_user
    ),
):
    """
    Delete a document and all of its indexed chunks.

    The document must belong to the authenticated user.
    """

    user_id = get_user_id(
        current_user
    )

    supabase = get_supabase_client()

    try:
        # -----------------------------------------------------
        # 1. VERIFY DOCUMENT OWNERSHIP
        # -----------------------------------------------------
        document_res = (
            supabase
            .table("documents")
            .select("id, filename")
            .eq("id", document_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

        if not document_res.data:
            raise HTTPException(
                status_code=404,
                detail="Document not found.",
            )

        # -----------------------------------------------------
        # 2. DELETE ALL VECTOR CHUNKS
        # -----------------------------------------------------
        (
            supabase
            .table("document_chunks")
            .delete()
            .eq("document_id", document_id)
            .eq("user_id", user_id)
            .execute()
        )

        # -----------------------------------------------------
        # 3. DELETE DOCUMENT RECORD
        # -----------------------------------------------------
        delete_res = (
            supabase
            .table("documents")
            .delete()
            .eq("id", document_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not delete_res.data:
            raise HTTPException(
                status_code=404,
                detail="Document not found or already deleted.",
            )

        filename = (
            document_res.data[0].get("filename")
            or "Document"
        )

        logger.info(
            "Document deleted successfully: "
            "document_id=%s, filename=%s, user_id=%s",
            document_id,
            filename,
            user_id,
        )

        return {
            "message": "Document deleted successfully.",
            "document_id": document_id,
        }

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception(
            "Failed to delete document %s for user %s.",
            document_id,
            user_id,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to delete the document. "
                "Please try again."
            ),
        ) from exc