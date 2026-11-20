import logging

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.config import get_settings


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
    # Port 1 refuses connections: a genuine connection failure, not a mocked exception.
    monkeypatch.setattr(get_settings(), "database_url", "postgresql://rag:rag@127.0.0.1:1/rag")
    with caplog.at_level(logging.WARNING, logger="app.health"):
        r = client.get("/health")

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
    monkeypatch.setattr(get_settings(), "api_key", "s3cret")
    assert client.get("/health").status_code == 200
