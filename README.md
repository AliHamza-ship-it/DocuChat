# DocuChat - Chat with Company Documents

A production-grade RAG application with FastAPI, Supabase pgvector, FAISS fallback, and React (Vite).

## Features
- **Semantic Chunking:** Advanced document parsing for PDF and DOCX.
- **Hybrid Vector Storage:** Supabase `pgvector` primary storage, local FAISS fallback.
- **Grounded Citations:** LLM answers include strict inline citations to original document pages.
- **Auth:** Complete email verification and secure login via Supabase.
- **Premium UI:** Glassmorphism styled React frontend.

## Quick Start
1. Run `pip install -r backend/requirements.txt`
2. Run `npm install` in the `/frontend` directory.
3. Start backend: `uvicorn backend.app.main:app --reload`
4. Start frontend: `npm run dev` in `/frontend`.