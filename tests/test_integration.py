"""End-to-end tests against real PostgreSQL + the real local models."""

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.config import get_settings
from app.db import connection
from app.ingest import ingest_bytes
from app.search import search

PAGE1 = (
    "Backups run every night at 02:30 UTC and are kept for 14 days. "
    "Restore with brightbay-ctl restore and a snapshot id."
)
PAGE2 = (
    "Single sign-on uses SAML 2.0 or OIDC. After 5 failed sign-in attempts the account is locked "
    "for 15 minutes."
)
DOC = (PAGE1 + "\n\n" + "filler. " * 5).encode()


@pytest.fixture
def client(clean_db):
    with TestClient(app) as c:
        yield c


def _two_page_doc() -> bytes:
    from tests.test_units import _pdf

    return _pdf(PAGE1, PAGE2)


def test_ingest_is_idempotent_and_replaces_changed_files(clean_db):
    first = ingest_bytes("a.txt", DOC)
    again = ingest_bytes("a.txt", DOC)
    assert not first.skipped and again.skipped and again.document_id == first.document_id

    changed = ingest_bytes("a.txt", b"Completely different content about invoices.")
    assert not changed.skipped
    with connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM documents").fetchone()["n"] == 1
        texts = [r["content"] for r in conn.execute("SELECT content FROM chunks").fetchall()]
    assert all("Backups" not in t for t in texts), "old chunks must be gone after replacement"


@pytest.mark.parametrize("mode", ["dense", "lexical", "hybrid", "hybrid_rerank"])
def test_every_mode_finds_the_right_page(clean_db, mode):
    ingest_bytes("guide.pdf", _two_page_doc(), title="guide")
    hits = search("how long are backups retained?", 3, mode)
    assert hits and hits[0].page == 1
    assert search("account lockout after failed sign-in", 3, mode)[0].page == 2


def test_lexical_channel_matches_exact_tokens_the_dense_channel_may_miss(clean_db):
    ingest_bytes("g.pdf", _two_page_doc(), title="g")
    hit = search("brightbay-ctl restore", 1, "lexical")[0]
    assert hit.page == 1 and hit.lexical_rank == 1


def test_hybrid_records_where_each_hit_came_from(clean_db):
    ingest_bytes("g.pdf", _two_page_doc(), title="g")
    top = search("SAML OIDC", 1, "hybrid_rerank")[0]
    assert top.page == 2 and top.rerank_score is not None
    assert top.dense_rank is not None and top.lexical_rank is not None


def test_blank_query_and_bad_mode(clean_db):
    assert search("   ", 3) == []
    with pytest.raises(ValueError):
        search("x", 3, "nope")  # type: ignore[arg-type]


def test_api_upload_list_ask_delete(client):
    r = client.post("/documents", files={"file": ("guide.pdf", _two_page_doc(), "application/pdf")})
    assert r.status_code == 201 and r.json()["pages"] == 2
    doc_id = r.json()["document_id"]

    docs = client.get("/documents").json()
    assert [d["source"] for d in docs] == ["guide.pdf"] and docs[0]["chunks"] >= 2

    ask = client.post("/ask", json={"query": "How long are backups kept?"}).json()
    assert ask["grounded"] and "14 days" in ask["answer"]
    assert (ask["citations"][0]["title"], ask["citations"][0]["page"]) == ("guide", 1)

    off_topic = client.post("/ask", json={"query": "What is the capital of France?"}).json()
    assert not off_topic["grounded"] and off_topic["citations"] == []

    assert client.delete(f"/documents/{doc_id}").status_code == 204
    assert client.delete(f"/documents/{doc_id}").status_code == 404
    assert client.get("/documents").json() == []


def test_api_rejects_bad_uploads(client):
    assert client.post("/documents", files={"file": ("x.exe", b"MZ", "x")}).status_code == 422
    assert client.post("/documents", files={"file": ("bad.pdf", b"nope", "x")}).status_code == 422
    # path components in the filename are stripped, never used as a path
    r = client.post("/documents", files={"file": ("../../etc/notes.txt", DOC, "text/plain")})
    assert r.status_code == 201
    assert client.get("/documents").json()[0]["source"] == "notes.txt"


def test_api_upload_size_limit(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    r = client.post("/documents", files={"file": ("a.txt", b"x" * 10, "text/plain")})
    assert r.status_code == 413


def test_api_validation(client):
    assert client.post("/search", json={"query": ""}).status_code == 422
    assert client.post("/search", json={"query": "x", "top_k": 999}).status_code == 422
    assert client.post("/search", json={"query": "x", "mode": "bogus"}).status_code == 422


def test_api_key_is_enforced_when_configured(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_key", "s3cret")
    assert client.get("/health").status_code == 200  # health stays open for orchestrators
    assert client.get("/documents").status_code == 401
    assert client.get("/documents", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/documents", headers={"X-API-Key": "s3cret"}).status_code == 200


def test_sql_injection_attempt_is_just_text(client):
    client.post("/documents", files={"file": ("a.txt", DOC, "text/plain")})
    r = client.post("/search", json={"query": "'; DROP TABLE chunks; --", "mode": "lexical"})
    assert r.status_code == 200
    assert client.get("/documents").json()[0]["chunks"] >= 1
