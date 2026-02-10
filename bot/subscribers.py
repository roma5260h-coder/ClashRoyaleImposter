import os
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, List, Optional

if TYPE_CHECKING:
    from aiogram.types import User


DEFAULT_DB_PATH = Path(__file__).resolve().with_name("subscribers.db")


def _db_path() -> Path:
    configured = os.getenv("BOT_USERS_DB_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_DB_PATH


def _connect() -> sqlite3.Connection:
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_subscribers_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                added_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                blocked_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_subscribers_active
            ON subscribers (is_active, updated_at)
            """
        )
        conn.commit()


def upsert_subscriber(user: "User") -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO subscribers (user_id, username, first_name, last_name, is_active, added_at, updated_at, blocked_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, NULL)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                is_active=1,
                updated_at=excluded.updated_at,
                blocked_at=NULL
            """,
            (
                int(user.id),
                user.username,
                user.first_name,
                user.last_name,
                now,
                now,
            ),
        )
        conn.commit()


def mark_blocked(user_id: int) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """
            UPDATE subscribers
            SET is_active=0, blocked_at=?, updated_at=?
            WHERE user_id=?
            """,
            (now, now, int(user_id)),
        )
        conn.commit()


def get_active_user_ids(limit: Optional[int] = None) -> List[int]:
    with _connect() as conn:
        query = "SELECT user_id FROM subscribers WHERE is_active=1 ORDER BY updated_at DESC"
        params: Iterable[int] = ()
        if limit is not None and limit > 0:
            query += " LIMIT ?"
            params = (int(limit),)
        rows = conn.execute(query, tuple(params)).fetchall()
    return [int(row[0]) for row in rows]


def subscribers_count(active_only: bool = False) -> int:
    with _connect() as conn:
        if active_only:
            row = conn.execute("SELECT COUNT(*) FROM subscribers WHERE is_active=1").fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()
    return int((row or [0])[0])


def subscribers_recent_count(days: int = 30, active_only: bool = False) -> int:
    if days <= 0:
        return 0
    since_ts = int(time.time()) - int(days) * 24 * 60 * 60
    query = "SELECT COUNT(DISTINCT user_id) FROM subscribers WHERE updated_at >= ?"
    params: List[object] = [since_ts]
    if active_only:
        query += " AND is_active=1"
    with _connect() as conn:
        row = conn.execute(query, tuple(params)).fetchone()
    return int((row or [0])[0])


def new_subscribers_count(days: int = 30) -> int:
    if days <= 0:
        return 0
    since_ts = int(time.time()) - int(days) * 24 * 60 * 60
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM subscribers WHERE added_at >= ?",
            (since_ts,),
        ).fetchone()
    return int((row or [0])[0])
