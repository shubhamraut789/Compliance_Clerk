"""
audit/logger.py
SQLite-backed audit trail for all LLM calls.

Schema:
  llm_logs(id, timestamp, doc_type, file_name, prompt, raw_response,
           parsed_ok, error_message, model, duration_ms)
"""

import sqlite3
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Logs every LLM prompt + raw response to a local SQLite database.

    Usage:
        audit = AuditLogger()
        log_id = audit.log(doc_type="lease_deed", file_name="foo.pdf",
                           prompt="...", raw_response="...",
                           parsed_ok=True, model="claude-sonnet-...")
    """

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS llm_logs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp       TEXT    NOT NULL,
        doc_type        TEXT    NOT NULL,
        file_name       TEXT    NOT NULL,
        model           TEXT    NOT NULL,
        prompt          TEXT    NOT NULL,
        raw_response    TEXT,
        parsed_ok       INTEGER NOT NULL DEFAULT 0,   -- 1=True, 0=False
        error_message   TEXT,
        duration_ms     INTEGER
    );
    """

    def __init__(self, db_path: Optional[str] = None):
        from config import DB_PATH
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(self.CREATE_TABLE_SQL)
            conn.commit()
        logger.debug("Audit DB ready at %s", self.db_path)

    def log(
        self,
        doc_type: str,
        file_name: str,
        prompt: str,
        raw_response: Optional[str] = None,
        parsed_ok: bool = False,
        error_message: Optional[str] = None,
        model: str = "",
        duration_ms: Optional[int] = None,
    ) -> int:
        """
        Insert one log row and return the new row id.
        """
        ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO llm_logs
                    (timestamp, doc_type, file_name, model,
                     prompt, raw_response, parsed_ok, error_message, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, doc_type, file_name, model,
                 prompt, raw_response,
                 1 if parsed_ok else 0,
                 error_message, duration_ms),
            )
            conn.commit()
            log_id = cursor.lastrowid

        logger.debug("Audit log #%d written (parsed_ok=%s)", log_id, parsed_ok)
        return log_id

    def get_recent(self, n: int = 20) -> list:
        """Return the n most recent log rows as dicts."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM llm_logs ORDER BY id DESC LIMIT ?", (n,)
            ).fetchall()
        return [dict(r) for r in rows]

    def summary(self) -> dict:
        """Return counts of total, parsed_ok, and failed entries."""
        with sqlite3.connect(self.db_path) as conn:
            total   = conn.execute("SELECT COUNT(*) FROM llm_logs").fetchone()[0]
            ok      = conn.execute("SELECT COUNT(*) FROM llm_logs WHERE parsed_ok=1").fetchone()[0]
            failed  = total - ok
        return {"total": total, "parsed_ok": ok, "failed": failed}