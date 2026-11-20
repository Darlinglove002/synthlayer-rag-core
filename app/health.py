"""Dependency checks behind `GET /health`."""

import logging

from app.db import get_pool

log = logging.getLogger(__name__)

PG_TIMEOUT_SECONDS = 2.0


def check_postgres() -> bool:
    """True if PostgreSQL answers `SELECT 1` through the connection pool within the timeout."""
    try:
        with get_pool().connection(timeout=PG_TIMEOUT_SECONDS) as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # any failure means "not ready"; the class goes to the log only
        log.warning("health: postgres check failed: %s", type(exc).__name__)
        return False
    return True


def run_checks() -> dict[str, bool]:
    """Component name -> healthy. Add a line here when the service gains a dependency."""
    return {"postgres": check_postgres()}
