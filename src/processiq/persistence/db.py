"""Shared SQLite connection factory for ProcessIQ persistence stores.

Separate from the LangGraph checkpointer connection (managed by SqliteSaver).
Both use the same DB file but different connections.
"""

import logging
import sqlite3
from pathlib import Path

from processiq.config import settings

logger = logging.getLogger(__name__)

_connection: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    """Get or create a shared SQLite connection for persistence stores."""
    global _connection
    if _connection is not None:
        return _connection

    db_path = Path(settings.persistence_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _connection = sqlite3.connect(str(db_path), check_same_thread=False)
    _connection.row_factory = sqlite3.Row
    _connection.execute("PRAGMA journal_mode=WAL")
    logger.info("Persistence DB connection opened: %s", db_path)
    return _connection


def close_connection() -> None:
    """Close the shared persistence DB connection."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
        logger.info("Persistence DB connection closed")
