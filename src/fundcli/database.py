"""Read command history from Atuin's SQLite database."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Iterator


class TimePeriod(Enum):
    """Time periods for filtering history."""
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    ALL = "all"


@dataclass
class HistoryEntry:
    """A single command history entry from Atuin."""
    id: str
    command: str
    timestamp: datetime
    duration_ns: int
    exit_code: int
    cwd: str
    hostname: str

    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        return self.duration_ns / 1_000_000

    @property
    def success(self) -> bool:
        """Whether the command succeeded (exit code 0)."""
        return self.exit_code == 0


def get_default_db_path() -> Path:
    """Get the default Atuin database path."""
    return Path.home() / ".local" / "share" / "atuin" / "history.db"


def get_period_start(period: TimePeriod) -> datetime | None:
    """Get the start datetime for a time period."""
    now = datetime.now()
    match period:
        case TimePeriod.DAY:
            return now - timedelta(days=1)
        case TimePeriod.WEEK:
            return now - timedelta(weeks=1)
        case TimePeriod.MONTH:
            return now - timedelta(days=30)
        case TimePeriod.YEAR:
            return now - timedelta(days=365)
        case TimePeriod.ALL:
            return None


def query_history(
    db_path: Path | None = None,
    period: TimePeriod = TimePeriod.MONTH,
    hostname: str | None = None,
    include_failed: bool = True,
) -> Iterator[HistoryEntry]:
    """
    Query command history from Atuin database.

    Args:
        db_path: Path to history.db. Defaults to ~/.local/share/atuin/history.db
        period: Time period to query (day, week, month, year, all)
        hostname: Filter by hostname (optional)
        include_failed: Include commands with non-zero exit codes

    Yields:
        HistoryEntry objects for each matching command
    """
    if db_path is None:
        db_path = get_default_db_path()

    if not db_path.exists():
        raise FileNotFoundError(f"Atuin database not found at {db_path}")

    # Build query
    query = """
        SELECT id, command, timestamp, duration, exit, cwd, hostname
        FROM history
        WHERE deleted_at IS NULL
    """
    params: list = []

    # Time filter (timestamp is in nanoseconds)
    period_start = get_period_start(period)
    if period_start:
        timestamp_ns = int(period_start.timestamp() * 1_000_000_000)
        query += " AND timestamp >= ?"
        params.append(timestamp_ns)

    # Hostname filter
    if hostname:
        query += " AND hostname LIKE ?"
        params.append(f"%{hostname}%")

    # Exit code filter
    if not include_failed:
        query += " AND exit = 0"

    query += " ORDER BY timestamp DESC"

    # Execute query
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.execute(query, params)
        for row in cursor:
            # Convert nanosecond timestamp to datetime
            timestamp = datetime.fromtimestamp(row["timestamp"] / 1_000_000_000)

            yield HistoryEntry(
                id=row["id"],
                command=row["command"],
                timestamp=timestamp,
                duration_ns=row["duration"],
                exit_code=row["exit"],
                cwd=row["cwd"],
                hostname=row["hostname"],
            )
    finally:
        conn.close()


def get_history_stats(db_path: Path | None = None) -> dict:
    """Get basic statistics about the history database."""
    if db_path is None:
        db_path = get_default_db_path()

    if not db_path.exists():
        raise FileNotFoundError(f"Atuin database not found at {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM history WHERE deleted_at IS NULL"
        ).fetchone()[0]

        oldest = conn.execute(
            "SELECT MIN(timestamp) FROM history WHERE deleted_at IS NULL"
        ).fetchone()[0]

        newest = conn.execute(
            "SELECT MAX(timestamp) FROM history WHERE deleted_at IS NULL"
        ).fetchone()[0]

        return {
            "total_commands": total,
            "oldest": datetime.fromtimestamp(oldest / 1_000_000_000) if oldest else None,
            "newest": datetime.fromtimestamp(newest / 1_000_000_000) if newest else None,
        }
    finally:
        conn.close()
