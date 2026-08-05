from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from typing import List
from backend.auth.supabase_auth import get_current_user
from backend.database.supabase_client import get_supabase_client
from backend.rag.parser import parse_pdf, parse_docx
from backend.rag.chunker import process_document_to_chunks
from backend.embeddings.vectorizer import embedding_service
from backend.storage.vector_store import vector_store
from backend.schemas.document import UploadResponse, DocumentResponse

router = APIRouter()

@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    filename = file.filename
    ext = filename.split(".")[-1].lower()

    if ext not in ["pdf", "docx"]:
        raise HTTPException(status_code=400, detail="Unsupported file type. Only PDF and DOCX files are allowed.")

    content_bytes = await file.read()

    # 1. Parse document
    if ext == "pdf":
        parsed_pages = parse_pdf(content_bytes, filename)
    else:
        parsed_pages = parse_docx(content_bytes, filename)

    if not parsed_pages:
        raise HTTPException(status_code=400, detail="Failed to extract text from document.")

    # 2. Chunk text recursively
    chunks_data = process_document_to_chunks(parsed_pages)
    if not chunks_data:
        raise HTTPException(status_code=400, detail="Document contains no indexable content.")

    user_id = current_user.id
    supabase = get_supabase_client()

    # 3. Create document record in Supabase
    doc_res = supabase.table("documents").insert({
        "filename": filename,
        "user_id": user_id
    }).execute()

    if not doc_res.data:
        raise HTTPException(status_code=500, detail="Failed to register document record.")

    document_id = doc_res.data[0]["id"]

    # 4. Generate batch embeddings
    texts_to_embed = [c["content"] for c in chunks_data]
    metadatas = [c["metadata"] for c in chunks_data]
    embeddings = embedding_service.generate_batch_embeddings(texts_to_embed)

    # 5. Store embeddings in vector store (pgvector + FAISS fallback)
    vector_store.store_chunks(
        document_id=document_id,
        user_id=user_id,
        chunks=texts_to_embed,
        embeddings=embeddings,
        metadatas=metadatas
    )

    return UploadResponse(
        message="Document uploaded, chunked, and indexed successfully.",
        document_id=document_id,
        chunks_processed=len(chunks_data)
    )

@router.get("/list", response_model=List[DocumentResponse])
def list_documents(current_user: dict = Depends(get_current_user)):
    supabase = get_supabase_client()
    res = supabase.table("documents").select("*").eq("user_id", current_user.id).order("created_at", desc=True).execute()
    return res.data or []