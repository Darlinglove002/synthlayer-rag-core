import hashlib
import logging
import time
from dataclasses import dataclass

from app.chunking import chunk_text
from app.config import get_settings
from app.db import connection
from app.loaders import load_pages
from app.models import embed_documents

log = logging.getLogger(__name__)


@dataclass
class IngestResult:
    document_id: int
    title: str
    pages: int
    chunks: int
    skipped: bool = False  # identical file already indexed


def ingest_bytes(filename: str, data: bytes, title: str | None = None) -> IngestResult:
    cfg = get_settings()
    started = time.perf_counter()
    digest = hashlib.sha256(data).hexdigest()
    title = title or filename.rsplit(".", 1)[0]

    with connection() as conn:
        row = conn.execute(
            "SELECT id, title, pages, sha256, (SELECT count(*) FROM chunks WHERE document_id = d.id) AS n "
            "FROM documents d WHERE source = %s",
            (filename,),
        ).fetchone()
        if row and row["sha256"] == digest:
            log.info("ingest %r: identical file already indexed, skipped", filename)
            return IngestResult(row["id"], row["title"], row["pages"], row["n"], skipped=True)

    pages = load_pages(filename, data)
    pieces: list[tuple[int, int, str]] = []  # (page, chunk_index, text)
    for page_no, text in pages:
        for idx, piece in enumerate(chunk_text(text, cfg.chunk_words, cfg.overlap_words)):
            pieces.append((page_no, idx, piece))
    vectors = embed_documents([p[2] for p in pieces])

    # One transaction: replace the old version (if any) and insert the new one atomically.
    with connection() as conn:
        conn.execute("DELETE FROM documents WHERE source = %s", (filename,))
        doc = conn.execute(
            "INSERT INTO documents (title, source, sha256, pages) VALUES (%s, %s, %s, %s) RETURNING id",
            (title, filename, digest, len(pages)),
        ).fetchone()
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (document_id, page, chunk_index, content, embedding) "
                "VALUES (%s, %s, %s, %s, %s)",
                [
                    (doc["id"], pg, ix, txt, vec)
                    for (pg, ix, txt), vec in zip(pieces, vectors, strict=True)
                ],
            )
    log.info(
        "ingest %r: %d pages, %d chunks in %.1fs",
        filename,
        len(pages),
        len(pieces),
        time.perf_counter() - started,
    )
    return IngestResult(doc["id"], title, len(pages), len(pieces))
