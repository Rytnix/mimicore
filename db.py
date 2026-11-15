"""
db.py — SQLite layer for Mimicore.

Tables:
  users     (id, username, password_hash, created_at)
  sessions  (token, user_id, created_at, expires_at)
  refs      (id, user_id, name, src_path, wav_path, raw_wav_path,
             duration, raw_duration, cleaned, language_hint, language,
             transcript, segments_json, status, error, uploaded_at, ready_at)
  jobs      (id, user_id, ref_id, ref_name, text, steps, speed,
             per_paragraph, batch_size, language, output_path, duration,
             status, return_code, log_json, created_at, started_at, finished_at)

Passwords are hashed with PBKDF2-HMAC-SHA256 (200k iters) using a per-user
salt — stdlib only, no extra dependency. Sessions are opaque random tokens
stored in a cookie; lookups go through the sessions table.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from hashlib import pbkdf2_hmac
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "mimicore.sqlite3"
VOICE_DATA = ROOT / "voice_data"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
VOICE_DATA.mkdir(parents=True, exist_ok=True)

# A single connection guarded by a re-entrant lock. Mimicore is single-process
# (FastAPI/uvicorn workers=1), so this is plenty; if we ever scale out we'd
# switch to per-request connections + WAL mode.
_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SESSION_TTL_DAYS = 30
PBKDF2_ITERS = 200_000


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode = WAL")
        _conn.execute("PRAGMA foreign_keys = ON")
        _migrate(_conn)
    return _conn


def _migrate(c: sqlite3.Connection) -> None:
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        created_at    TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sessions (
        token       TEXT PRIMARY KEY,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at  TEXT NOT NULL,
        expires_at  TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

    CREATE TABLE IF NOT EXISTS refs (
        id              TEXT PRIMARY KEY,
        user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name            TEXT NOT NULL,
        src_path        TEXT NOT NULL,
        wav_path        TEXT NOT NULL,
        raw_wav_path    TEXT,
        duration        REAL DEFAULT 0,
        raw_duration    REAL DEFAULT 0,
        cleaned         INTEGER DEFAULT 0,
        language_hint   TEXT,
        language        TEXT,
        transcript      TEXT DEFAULT '',
        segments_json   TEXT DEFAULT '[]',
        status          TEXT DEFAULT 'queued',
        error           TEXT,
        uploaded_at     TEXT NOT NULL,
        ready_at        TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_refs_user ON refs(user_id);

    CREATE TABLE IF NOT EXISTS jobs (
        id            TEXT PRIMARY KEY,
        user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        ref_id        TEXT REFERENCES refs(id) ON DELETE SET NULL,
        ref_name      TEXT,
        text          TEXT NOT NULL,
        steps         INTEGER DEFAULT 32,
        speed         REAL DEFAULT 1.0,
        per_paragraph INTEGER DEFAULT 0,
        batch_size    INTEGER DEFAULT 4,
        language      TEXT,
        output_path   TEXT,
        duration      REAL,
        status        TEXT DEFAULT 'queued',
        return_code   INTEGER,
        log_json      TEXT DEFAULT '[]',
        created_at    TEXT NOT NULL,
        started_at    TEXT,
        finished_at   TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
    """)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERS)
    return f"pbkdf2_sha256${PBKDF2_ITERS}${salt.hex()}${h.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    salt = bytes.fromhex(salt_hex)
    h = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
    # Constant-time compare.
    return secrets.compare_digest(h.hex(), hash_hex)


def create_user(username: str, password: str) -> dict[str, Any]:
    """Returns the new user dict. Raises ValueError on validation/duplication."""
    username = (username or "").strip()
    if not username or len(username) < 3:
        raise ValueError("username must be at least 3 characters")
    if not username.replace("_", "").replace("-", "").isalnum():
        raise ValueError("username may only contain letters, digits, _ and -")
    if not password or len(password) < 6:
        raise ValueError("password must be at least 6 characters")

    with _lock:
        c = _connect()
        try:
            c.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
                (username, _hash_password(password), now_iso()),
            )
        except sqlite3.IntegrityError:
            raise ValueError("username already taken")
        row = c.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()

    # Eagerly create the user's voice_data subtree so it always exists.
    user_dirs(row["username"])
    return _user_dict(row)


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    with _lock:
        row = _connect().execute(
            "SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)
        ).fetchone()
    if not row:
        return None
    if not _verify_password(password, row["password_hash"]):
        return None
    return _user_dict(row)


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with _lock:
        row = _connect().execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _user_dict(row) if row else None


def _user_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "username": row["username"], "created_at": row["created_at"]}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)).isoformat()
    with _lock:
        _connect().execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
            (token, user_id, now_iso(), expires),
        )
    return token


def revoke_session(token: str) -> None:
    with _lock:
        _connect().execute("DELETE FROM sessions WHERE token=?", (token,))


def user_for_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    with _lock:
        row = _connect().execute(
            "SELECT s.expires_at, u.* FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token=?",
            (token,),
        ).fetchone()
    if not row:
        return None
    if row["expires_at"] and row["expires_at"] < now_iso():
        revoke_session(token)
        return None
    return {"id": row["id"], "username": row["username"], "created_at": row["created_at"]}


# ---------------------------------------------------------------------------
# Per-user filesystem layout
# ---------------------------------------------------------------------------
def user_dirs(username: str) -> dict[str, Path]:
    base = VOICE_DATA / username
    refs = base / "reference_audio"
    outs = base / "converted_audio"
    refs.mkdir(parents=True, exist_ok=True)
    outs.mkdir(parents=True, exist_ok=True)
    return {"base": base, "refs": refs, "outs": outs}


# ---------------------------------------------------------------------------
# Refs
# ---------------------------------------------------------------------------
def insert_ref(user_id: int, ref: dict[str, Any]) -> None:
    with _lock:
        _connect().execute(
            """INSERT INTO refs (id, user_id, name, src_path, wav_path, raw_wav_path,
               duration, raw_duration, cleaned, language_hint, language, transcript,
               segments_json, status, error, uploaded_at, ready_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ref["id"], user_id, ref["name"], ref["src_path"], ref["wav_path"],
                ref.get("raw_wav_path"), float(ref.get("duration", 0)),
                float(ref.get("raw_duration", 0)), 1 if ref.get("cleaned") else 0,
                ref.get("language_hint"), ref.get("language"),
                ref.get("transcript", ""), json.dumps(ref.get("segments", [])),
                ref.get("status", "queued"), ref.get("error"),
                ref.get("uploaded_at", now_iso()), ref.get("ready_at"),
            ),
        )


def update_ref(ref_id: str, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values())
    with _lock:
        _connect().execute(f"UPDATE refs SET {cols} WHERE id=?", (*vals, ref_id))


def get_ref(ref_id: str, user_id: int | None = None) -> dict[str, Any] | None:
    with _lock:
        if user_id is None:
            row = _connect().execute("SELECT * FROM refs WHERE id=?", (ref_id,)).fetchone()
        else:
            row = _connect().execute(
                "SELECT * FROM refs WHERE id=? AND user_id=?", (ref_id, user_id)
            ).fetchone()
    return _ref_dict(row) if row else None


def list_refs(user_id: int) -> list[dict[str, Any]]:
    with _lock:
        rows = _connect().execute(
            "SELECT * FROM refs WHERE user_id=? ORDER BY uploaded_at DESC", (user_id,)
        ).fetchall()
    return [_ref_dict(r) for r in rows]


def delete_ref(ref_id: str, user_id: int) -> dict[str, Any] | None:
    ref = get_ref(ref_id, user_id)
    if not ref:
        return None
    with _lock:
        _connect().execute("DELETE FROM refs WHERE id=? AND user_id=?", (ref_id, user_id))
    return ref


def _ref_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "src_path": row["src_path"],
        "wav_path": row["wav_path"],
        "raw_wav_path": row["raw_wav_path"],
        "duration": row["duration"],
        "raw_duration": row["raw_duration"],
        "cleaned": bool(row["cleaned"]),
        "language_hint": row["language_hint"],
        "language": row["language"],
        "transcript": row["transcript"] or "",
        "segments": json.loads(row["segments_json"] or "[]"),
        "status": row["status"],
        "error": row["error"],
        "uploaded_at": row["uploaded_at"],
        "ready_at": row["ready_at"],
    }


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
def insert_job(user_id: int, job: dict[str, Any]) -> None:
    with _lock:
        _connect().execute(
            """INSERT INTO jobs (id, user_id, ref_id, ref_name, text, steps, speed,
               per_paragraph, batch_size, language, output_path, duration, status,
               return_code, log_json, created_at, started_at, finished_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job["id"], user_id, job.get("ref_id"), job.get("ref_name"),
                job["text"], int(job.get("steps", 32)), float(job.get("speed", 1.0)),
                1 if job.get("per_paragraph") else 0, int(job.get("batch_size", 4)),
                job.get("language"), job.get("output_path"), job.get("duration"),
                job.get("status", "queued"), job.get("return_code"),
                json.dumps(job.get("log", [])), job.get("created_at", now_iso()),
                job.get("started_at"), job.get("finished_at"),
            ),
        )


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    if "log" in fields:
        fields["log_json"] = json.dumps(fields.pop("log"))
    cols = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values())
    with _lock:
        _connect().execute(f"UPDATE jobs SET {cols} WHERE id=?", (*vals, job_id))


def get_job(job_id: str, user_id: int | None = None) -> dict[str, Any] | None:
    with _lock:
        if user_id is None:
            row = _connect().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        else:
            row = _connect().execute(
                "SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user_id)
            ).fetchone()
    return _job_dict(row) if row else None


def list_jobs(user_id: int) -> list[dict[str, Any]]:
    with _lock:
        rows = _connect().execute(
            "SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
    return [_job_dict(r) for r in rows]


def _job_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "ref_id": row["ref_id"],
        "ref_name": row["ref_name"],
        "text": row["text"],
        "steps": row["steps"],
        "speed": row["speed"],
        "per_paragraph": bool(row["per_paragraph"]),
        "batch_size": row["batch_size"],
        "language": row["language"],
        "output_path": row["output_path"],
        "duration": row["duration"],
        "status": row["status"],
        "return_code": row["return_code"],
        "log": json.loads(row["log_json"] or "[]"),
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }
