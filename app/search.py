"""Two-channel retrieval inside one PostgreSQL, fused with RRF, then cross-encoder reranked."""

from dataclasses import dataclass, field
from typing import Literal

from app.config import get_settings
from app.db import connection
from app.models import embed_query, rerank_scores

Mode = Literal["dense", "lexical", "hybrid", "hybrid_rerank"]
MODES: tuple[str, ...] = ("dense", "lexical", "hybrid", "hybrid_rerank")


@dataclass
class Hit:
    chunk_id: int
    document_id: int
    title: str
    page: int
    content: str
    score: float = 0.0  # score of the final ordering (rrf, or rerank logit)
    dense_rank: int | None = None
    lexical_rank: int | None = None
    rerank_score: float | None = None
    extra: dict = field(default_factory=dict)


def dense_ids(conn, qvec, n: int) -> list[int]:
    rows = conn.execute(
        "SELECT id FROM chunks ORDER BY embedding <=> %s LIMIT %s", (qvec, n)
    ).fetchall()
    return [r["id"] for r in rows]


def lexical_ids(conn, query: str, n: int) -> list[int]:
    """Full-text channel. plainto_tsquery ANDs every term, which is far too strict for a
    natural-language question, so the query is rewritten to OR; ts_rank_cd then favours
    chunks that match many terms close together."""
    rows = conn.execute(
        """
        SELECT c.id
        FROM chunks c, (SELECT replace(plainto_tsquery('english', %s)::text, '&', '|')::tsquery AS q) s
        WHERE c.tsv @@ s.q
        ORDER BY ts_rank_cd(c.tsv, s.q) DESC, c.id
        LIMIT %s
        """,
        (query, n),
    ).fetchall()
    return [r["id"] for r in rows]


def rrf(rankings: list[list[int]], k: int) -> dict[int, float]:
    """Reciprocal Rank Fusion: score(d) = sum over channels of 1 / (k + rank)."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores


def _fetch(conn, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    rows = conn.execute(
        "SELECT c.id, c.document_id, d.title, c.page, c.content "
        "FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.id = ANY(%s)",
        (ids,),
    ).fetchall()
    return {r["id"]: r for r in rows}


def search(query: str, top_k: int = 5, mode: Mode = "hybrid_rerank") -> list[Hit]:
    cfg = get_settings()
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")
    query = query.strip()
    if not query:
        return []

    with connection() as conn:
        d_ids = dense_ids(conn, embed_query(query), cfg.candidates) if mode != "lexical" else []
        l_ids = lexical_ids(conn, query, cfg.candidates) if mode != "dense" else []
        d_rank = {cid: i for i, cid in enumerate(d_ids, 1)}
        l_rank = {cid: i for i, cid in enumerate(l_ids, 1)}

        fused = rrf([r for r in (d_ids, l_ids) if r], cfg.rrf_k)
        order = sorted(fused, key=lambda c: (-fused[c], c))
        pool = order[: cfg.rerank_pool] if mode == "hybrid_rerank" else order[:top_k]
        rows = _fetch(conn, pool)

    hits = [
        Hit(
            chunk_id=cid,
            document_id=rows[cid]["document_id"],
            title=rows[cid]["title"],
            page=rows[cid]["page"],
            content=rows[cid]["content"],
            score=fused[cid],
            dense_rank=d_rank.get(cid),
            lexical_rank=l_rank.get(cid),
        )
        for cid in pool
    ]
    if mode == "hybrid_rerank":
        for hit, s in zip(hits, rerank_scores(query, [h.content for h in hits]), strict=True):
            hit.rerank_score = s
            hit.score = s
        hits.sort(key=lambda h: (-h.score, h.chunk_id))
    return hits[:top_k]
