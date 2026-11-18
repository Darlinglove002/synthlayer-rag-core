import os
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

# Point the app at a throwaway database BEFORE any app module reads its settings.
_base = os.environ.get("DATABASE_URL", "postgresql://rag:rag@localhost:5444/rag")
_parts = urlsplit(_base)
_ADMIN = urlunsplit(_parts._replace(path="/postgres"))
os.environ["DATABASE_URL"] = urlunsplit(_parts._replace(path="/rag_test"))
os.environ.pop("API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)


def _db_available() -> bool:
    try:
        psycopg.connect(_ADMIN, connect_timeout=3).close()
        return True
    except psycopg.OperationalError:
        return False


@pytest.fixture(scope="session")
def database():
    if not _db_available():
        pytest.skip("PostgreSQL not reachable (docker compose up -d db)")
    with psycopg.connect(_ADMIN, autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS rag_test WITH (FORCE)")
        conn.execute("CREATE DATABASE rag_test")
    from app.db import close_pool, get_pool

    get_pool()
    yield
    close_pool()


@pytest.fixture
def clean_db(database):
    from app.db import connection

    with connection() as conn:
        conn.execute("TRUNCATE documents RESTART IDENTITY CASCADE")
    yield


def pytest_collection_modifyitems(items):
    for item in items:
        if "clean_db" in item.fixturenames or "database" in item.fixturenames:
            item.add_marker(pytest.mark.integration)
