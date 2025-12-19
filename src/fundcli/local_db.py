"""Local SQLite database for storing unknown executable classifications."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator


def get_data_dir() -> Path:
    """Get the local data directory for fundcli."""
    return Path.home() / ".local" / "share" / "fundcli"


def get_db_path() -> Path:
    """Get the path to the unknowns database."""
    return get_data_dir() / "unknowns.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS unknowns (
    executable TEXT PRIMARY KEY,
    path TEXT,
    file_type TEXT,
    classification TEXT,
    copyright_found TEXT,
    help_text TEXT,
    suggested_project TEXT,
    user_notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS exception_list (
    executable TEXT PRIMARY KEY,
    reason TEXT,
    created_at TEXT
);
"""


@dataclass
class UnknownExecutable:
    """Record for an unknown executable."""
    executable: str
    path: str | None = None
    file_type: str | None = None  # 'script', 'binary', 'not_found'
    classification: str | None = None  # 'system', 'third_party', 'user', 'ignored'
    copyright_found: str | None = None
    help_text: str | None = None
    suggested_project: str | None = None
    user_notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class LocalDatabase:
    """SQLite database for storing unknown executable info."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_db_path()
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Ensure database and tables exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_unknown(self, executable: str) -> UnknownExecutable | None:
        """Get an unknown executable by name."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM unknowns WHERE executable = ?",
                (executable,)
            ).fetchone()
            if row:
                return UnknownExecutable(**dict(row))
            return None
        finally:
            conn.close()

    def save_unknown(self, unknown: UnknownExecutable) -> None:
        """Save or update an unknown executable."""
        now = datetime.now().isoformat()
        conn = self._connect()
        try:
            existing = self.get_unknown(unknown.executable)
            if existing:
                conn.execute("""
                    UPDATE unknowns SET
                        path = ?,
                        file_type = ?,
                        classification = ?,
                        copyright_found = ?,
                        help_text = ?,
                        suggested_project = ?,
                        user_notes = ?,
                        updated_at = ?
                    WHERE executable = ?
                """, (
                    unknown.path,
                    unknown.file_type,
                    unknown.classification,
                    unknown.copyright_found,
                    unknown.help_text,
                    unknown.suggested_project,
                    unknown.user_notes,
                    now,
                    unknown.executable,
                ))
            else:
                conn.execute("""
                    INSERT INTO unknowns (
                        executable, path, file_type, classification,
                        copyright_found, help_text, suggested_project,
                        user_notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    unknown.executable,
                    unknown.path,
                    unknown.file_type,
                    unknown.classification,
                    unknown.copyright_found,
                    unknown.help_text,
                    unknown.suggested_project,
                    unknown.user_notes,
                    now,
                    now,
                ))
            conn.commit()
        finally:
            conn.close()

    def list_unknowns(self) -> list[UnknownExecutable]:
        """List all unknown executables."""
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM unknowns ORDER BY executable").fetchall()
            return [UnknownExecutable(**dict(row)) for row in rows]
        finally:
            conn.close()

    def delete_unknown(self, executable: str) -> bool:
        """Delete an unknown executable record."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM unknowns WHERE executable = ?",
                (executable,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def clear_all(self) -> int:
        """Clear all unknown records. Returns count deleted."""
        conn = self._connect()
        try:
            cursor = conn.execute("DELETE FROM unknowns")
            count = cursor.rowcount
            conn.execute("DELETE FROM exception_list")
            conn.commit()
            return count
        finally:
            conn.close()

    def is_excepted(self, executable: str) -> bool:
        """Check if executable is in exception list."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM exception_list WHERE executable = ?",
                (executable,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def add_exception(self, executable: str, reason: str) -> None:
        """Add executable to exception list."""
        now = datetime.now().isoformat()
        conn = self._connect()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO exception_list (executable, reason, created_at)
                VALUES (?, ?, ?)
            """, (executable, reason, now))
            conn.commit()
        finally:
            conn.close()

    def remove_exception(self, executable: str) -> bool:
        """Remove executable from exception list."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM exception_list WHERE executable = ?",
                (executable,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def list_exceptions(self) -> list[tuple[str, str]]:
        """List all exceptions as (executable, reason) tuples."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT executable, reason FROM exception_list ORDER BY executable"
            ).fetchall()
            return [(row["executable"], row["reason"]) for row in rows]
        finally:
            conn.close()

    def get_classified_as(self, classification: str) -> list[str]:
        """Get all executables with a specific classification."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT executable FROM unknowns WHERE classification = ?",
                (classification,)
            ).fetchall()
            return [row["executable"] for row in rows]
        finally:
            conn.close()

    def db_exists(self) -> bool:
        """Check if database file exists."""
        return self.db_path.exists()
