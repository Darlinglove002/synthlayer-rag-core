import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import answer as answer_mod
from app.config import get_settings
from app.db import close_pool, connection, get_pool
from app.health import run_checks
from app.ingest import ingest_bytes
from app.loaders import UnsupportedFile
from app.logging_config import configure_logging
from app.search import MODES, Mode, search

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    get_pool()
    log.info(
        "started: PostgreSQL pool ready, answers are %s",
        "LLM-written" if get_settings().anthropic_api_key else "extractive",
    )
    yield
    close_pool()
    log.info("stopped")


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


@app.get(
    "/health",
    responses={503: {"description": "a dependency is down; `failed` names it"}},
)
def health() -> JSONResponse:
    """Readiness: runs a real `SELECT 1` through the connection pool.

    200 when every dependency answers, 503 with the failing component otherwise. It stays
    open (no API key) so orchestrators can call it.
    """
    checks = run_checks()
    failed = [name for name, ok in checks.items() if not ok]
    body: dict[str, Any] = {
        "status": "unavailable" if failed else "ok",
        "checks": {name: "ok" if ok else "down" for name, ok in checks.items()},
    }
    if failed:
        body["failed"] = failed
        return JSONResponse(body, status_code=503)
    body["modes"] = list(MODES)
    body["llm"] = bool(get_settings().anthropic_api_key)
    return JSONResponse(body)


@app.get("/documents", dependencies=[Auth])
def list_documents() -> list[dict[str, Any]]:
    with connection() as conn:
        return conn.execute(
            "SELECT d.id, d.title, d.source, d.pages, d.created_at, count(c.id) AS chunks "
            "FROM documents d LEFT JOIN chunks c ON c.document_id = d.id "
            "GROUP BY d.id ORDER BY d.id"
        ).fetchall()


@app.post("/documents", dependencies=[Auth], status_code=201)
def upload_document(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    cfg = get_settings()
    limit = cfg.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    # Only the basename is stored, and it is never used as a filesystem path.
    name = (file.filename or "upload").replace("\\", "/").rsplit("/", 1)[-1][:200]
    if len(data) > limit:
        log.info("rejected upload %r: larger than %d MB", name, cfg.max_upload_mb)
        raise HTTPException(413, f"file larger than {cfg.max_upload_mb} MB")
    try:
        result = ingest_bytes(name, data)
    except UnsupportedFile as exc:
        log.info("rejected upload %r: %s", name, exc)
        raise HTTPException(422, str(exc)) from exc
    return asdict(result)


@app.delete("/documents/{doc_id}", dependencies=[Auth], status_code=204)
def delete_document(doc_id: int) -> None:
    with connection() as conn:
        deleted = conn.execute(
            "DELETE FROM documents WHERE id = %s RETURNING id", (doc_id,)
        ).fetchone()
    if not deleted:
        raise HTTPException(404, "document not found")
    log.info("deleted document %d", doc_id)


@app.post("/search", dependencies=[Auth])
def search_endpoint(req: SearchRequest) -> dict[str, Any]:
    return {"hits": [asdict(h) for h in search(req.query, req.top_k, req.mode)]}


@app.post("/ask", dependencies=[Auth])
def ask(req: SearchRequest) -> dict[str, Any]:
    hits = search(req.query, req.top_k, "hybrid_rerank")
    result = answer_mod.answer(req.query, hits)
    # The question text is never logged: it may contain anything the user typed.
    log.info(
        "ask: %d hits, grounded=%s, generator=%s", len(hits), result.grounded, result.generator
    )
    return {
        "answer": result.text,
        "grounded": result.grounded,
        "generator": result.generator,
        "citations": [asdict(c) for c in result.citations],
        "sources": [
            {"title": h.title, "page": h.page, "score": h.score, "content": h.content} for h in hits
        ],
    }
