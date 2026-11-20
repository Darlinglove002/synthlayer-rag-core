import logging

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from app import health
from app.api import app


@pytest.fixture
def client(database):
    with TestClient(app) as c:
        yield c


def test_health_is_200_and_reports_postgres_when_everything_works(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["checks"] == {"postgres": "ok"}
    assert body["modes"] == ["dense", "lexical", "hybrid", "hybrid_rerank"]
    assert "failed" not in body


def test_health_is_503_and_names_postgres_when_it_cannot_be_reached(client, monkeypatch, caplog):
    # A pool aimed at a closed port: a genuine connection-refused, not a mocked exception.
    dead = ConnectionPool("postgresql://rag:rag@127.0.0.1:1/rag", min_size=0, max_size=1, open=True)
    monkeypatch.setattr(health, "get_pool", lambda: dead)
    monkeypatch.setattr(health, "PG_TIMEOUT_SECONDS", 0.3)
    try:
        with caplog.at_level(logging.WARNING, logger="app.health"):
            r = client.get("/health")
    finally:
        dead.close(timeout=2)

    assert r.status_code == 503
    assert r.json() == {
        "status": "unavailable",
        "checks": {"postgres": "down"},
        "failed": ["postgres"],
    }
    # Details go to the log, not to an endpoint that is open to anyone.
    assert "127.0.0.1" not in r.text and "Error" not in r.text
    assert "postgres check failed" in caplog.text


def test_health_stays_open_when_an_api_key_is_configured(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "api_key", "s3cret")
    assert client.get("/health").status_code == 200
