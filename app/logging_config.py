"""One place that decides how the service logs.

Every record is a single line on stderr: time, level, logger name, message. The level comes
from `LOG_LEVEL` (default INFO). `configure_logging()` is called once at startup; calling it
again is harmless, and it leaves handlers that a host process (pytest, uvicorn, an embedding
application) already installed alone.
"""

import logging
import os

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging(level: str | None = None) -> None:
    name = (level or os.environ.get("LOG_LEVEL") or "INFO").upper()
    if name not in logging.getLevelNamesMapping():
        name = "INFO"  # a typo in LOG_LEVEL must not stop the service from starting
    root = logging.getLogger()
    root.setLevel(name)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(handler)
