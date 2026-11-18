import hmac
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import answer as answer_mod
from app.config import get_settings
from app.db import close_pool, connection, get_pool
from app.ingest import ingest_bytes
from app.loaders import UnsupportedFile
from app.search import MODES, Mode, search


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_pool()
    yield
    close_pool()


app = FastAPI(title="synthlayer-rag-core", version="0.1.0", lifespan=lifespan)


def require_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().api_key
    if expected and not hmac.compare_digest(x_api_key or "", expected):
        raise HTTPException(401, "invalid or missing X-API-Key")


Auth = Depends(require_key)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(5, ge=1, le=20)
    mode: Mode = "hybrid_rerank"


@app.get("/health")
def health():
    with connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok", "modes": list(MODES), "llm": bool(get_settings().anthropic_api_key)}


@app.get("/documents", dependencies=[Auth])
def list_documents():
    with connection() as conn:
        return conn.execute(
            "SELECT d.id, d.title, d.source, d.pages, d.created_at, count(c.id) AS chunks "
            "FROM documents d LEFT JOIN chunks c ON c.document_id = d.id "
            "GROUP BY d.id ORDER BY d.id"
        ).fetchall()


@app.post("/documents", dependencies=[Auth], status_code=201)
def upload_document(file: Annotated[UploadFile, File()]):
    cfg = get_settings()
    limit = cfg.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"file larger than {cfg.max_upload_mb} MB")
    # Only the basename is stored, and it is never used as a filesystem path.
    name = (file.filename or "upload").replace("\\", "/").rsplit("/", 1)[-1][:200]
    try:
        result = ingest_bytes(name, data)
    except UnsupportedFile as exc:
        raise HTTPException(422, str(exc)) from exc
    return asdict(result)


@app.delete("/documents/{doc_id}", dependencies=[Auth], status_code=204)
def delete_document(doc_id: int):
    with connection() as conn:
        deleted = conn.execute("DELETE FROM documents WHERE id = %s RETURNING id", (doc_id,)).fetchone()
    if not deleted:
        raise HTTPException(404, "document not found")


@app.post("/search", dependencies=[Auth])
def search_endpoint(req: SearchRequest):
    return {"hits": [asdict(h) for h in search(req.query, req.top_k, req.mode)]}


@app.post("/ask", dependencies=[Auth])
def ask(req: SearchRequest):
    hits = search(req.query, req.top_k, "hybrid_rerank")
    result = answer_mod.answer(req.query, hits)
    return {
        "answer": result.text,
        "grounded": result.grounded,
        "generator": result.generator,
        "citations": [asdict(c) for c in result.citations],
        "sources": [
            {"title": h.title, "page": h.page, "score": h.score, "content": h.content} for h in hits
        ],
    }
