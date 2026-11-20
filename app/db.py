import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_path TEXT NOT NULL,
    original_name TEXT NOT NULL,
    scheduled_at TEXT,              -- local time ISO string, NULL = post now
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,         -- youtube | instagram | facebook
    title TEXT,                     -- YouTube only
    caption TEXT,
    privacy TEXT,                   -- YouTube only: public | unlisted | private
    status TEXT NOT NULL,           -- pending | uploading | done | failed | cancelled
    progress TEXT,
    result_url TEXT,
    error TEXT,
    updated_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as c:
        c.executescript(SCHEMA)
        # Anything stuck "uploading" from a previous crash goes back to failed so it can be retried.
        c.execute(
            "UPDATE jobs SET status='failed', error='App was closed during upload', updated_at=? "
            "WHERE status='uploading'",
            (now_iso(),),
        )


def create_post(video_path: str, original_name: str, scheduled_at: str | None, jobs: list[dict]) -> int:
    with connect() as c:
        cur = c.execute(
            "INSERT INTO posts (video_path, original_name, scheduled_at, created_at) VALUES (?,?,?,?)",
            (video_path, original_name, scheduled_at, now_iso()),
        )
        post_id = cur.lastrowid
        for j in jobs:
            c.execute(
                "INSERT INTO jobs (post_id, platform, title, caption, privacy, status, updated_at) "
                "VALUES (?,?,?,?,?, 'pending', ?)",
                (post_id, j["platform"], j.get("title"), j.get("caption"), j.get("privacy"), now_iso()),
            )
        return post_id


def update_job(job_id: int, **fields):
    fields["updated_at"] = now_iso()
    cols = ", ".join(f"{k}=?" for k in fields)
    with connect() as c:
        c.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))


def claim_due_jobs() -> list[dict]:
    """Atomically mark due pending jobs as uploading and return them."""
    now = now_iso()
    with connect() as c:
        rows = c.execute(
            "SELECT j.*, p.video_path FROM jobs j JOIN posts p ON p.id = j.post_id "
            "WHERE j.status='pending' AND (p.scheduled_at IS NULL OR p.scheduled_at <= ?)",
            (now,),
        ).fetchall()
        for r in rows:
            c.execute(
                "UPDATE jobs SET status='uploading', progress='Starting', error=NULL, updated_at=? WHERE id=?",
                (now, r["id"]),
            )
        return [dict(r) for r in rows]


def list_posts(limit: int = 100) -> list[dict]:
    with connect() as c:
        posts = [dict(r) for r in c.execute("SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,))]
        for p in posts:
            p["jobs"] = [dict(r) for r in c.execute("SELECT * FROM jobs WHERE post_id=? ORDER BY id", (p["id"],))]
        return posts


def get_job(job_id: int) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(r) if r else None


def get_post(post_id: int) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        if not r:
            return None
        p = dict(r)
        p["jobs"] = [dict(x) for x in c.execute("SELECT * FROM jobs WHERE post_id=?", (post_id,))]
        return p


def delete_post(post_id: int):
    with connect() as c:
        c.execute("DELETE FROM posts WHERE id=?", (post_id,))
