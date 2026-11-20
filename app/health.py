"""Dependency checks behind `GET /health`."""

import logging

import psycopg

from app.config import get_settings

log = logging.getLogger(__name__)

# libpq takes whole seconds and rounds anything below 2 up to 2.
CONNECT_TIMEOUT_SECONDS = 2
STATEMENT_TIMEOUT_MS = 2000


def check_postgres() -> bool:
    """True if PostgreSQL answers `SELECT 1` on a fresh connection within a few seconds.

    This uses a dedicated short-lived connection, not the pool. A pool hands back an idle
    connection that was fine a minute ago, and on a frozen server `SELECT 1` over it never
    returns: the first version of this check hung until the client gave up (reproduced with
    `docker pause` on the database container). A fresh connection is bounded by libpq's
    connect timeout (2 s per resolved address), and the statement timeout bounds the query.
    It does not measure pool saturation; that is a different question from "is the database
    there".
    """
    try:
        with psycopg.connect(
            get_settings().database_url,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
            autocommit=True,
        ) as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # any failure means "not ready"; the class goes to the log only
        log.warning("postgres check failed: %s", type(exc).__name__)
        return False
    return True


def run_checks() -> dict[str, bool]:
    """Component name -> healthy. Add a line here when the service gains a dependency."""
    return {"postgres": check_postgres()}
