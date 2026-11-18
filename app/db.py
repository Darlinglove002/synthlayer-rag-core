from contextlib import contextmanager
from pathlib import Path

from pgvector.psycopg import register_vector
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

_pool: ConnectionPool | None = None
SCHEMA = Path(__file__).with_name("schema.sql")


def _configure(conn: Connection) -> None:
    register_vector(conn)
    conn.row_factory = dict_row


def init_schema(database_url: str | None = None) -> None:
    """Create the extension and tables. The vector type must exist before the pool registers it."""
    import psycopg

    with psycopg.connect(database_url or get_settings().database_url, autocommit=True) as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        init_schema()
        _pool = ConnectionPool(
            get_settings().database_url, min_size=1, max_size=8, configure=_configure, open=True
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection():
    with get_pool().connection() as conn:
        yield conn
