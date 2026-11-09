"""SQLite access. One file, zero setup; `make reset` rebuilds it from seed data."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
def db_path() -> Path:
    return Path(os.environ.get("MATCHBOOK_DB", ROOT / "backend" / "matchbook.db"))
SCHEMA = Path(__file__).with_name("schema.sql")

_write_lock = threading.RLock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def tx():
    """Serialized write transaction."""
    with _write_lock:
        conn = connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def query(sql: str, params: tuple | list = ()) -> list[dict]:
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def query_one(sql: str, params: tuple | list = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def insert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(row.values()))


def update(conn: sqlite3.Connection, table: str, key: str, row: dict) -> None:
    sets = ", ".join(f"{k} = ?" for k in row)
    conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*row.values(), key])


def loads(s: str | None, default=None):
    return json.loads(s) if s else default


def reset_db() -> None:
    with _write_lock:
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(db_path()) + suffix)
            if p.exists():
                p.unlink()
        conn = connect()
        conn.executescript(SCHEMA.read_text())
        conn.commit()
        conn.close()
