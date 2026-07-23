"""SQLite-backed storage for deduplication and history. One file, no server."""
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "records.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    dedup_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT,
    source TEXT NOT NULL,
    country TEXT NOT NULL,
    category TEXT NOT NULL,
    buyer TEXT,
    deadline TEXT,
    value_estimate TEXT,
    keywords_matched TEXT,
    reason TEXT,
    date_first_seen TEXT NOT NULL,
    date_last_seen TEXT NOT NULL,
    expired INTEGER NOT NULL DEFAULT 0
);
"""


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_records(records) -> list:
    """Insert new records, refresh last_seen on existing ones. Returns the subset that are brand new this run."""
    today = date.today().isoformat()
    new_records = []
    with connect() as conn:
        for r in records:
            key = r.dedup_key()
            existing = conn.execute(
                "SELECT dedup_key FROM records WHERE dedup_key = ?", (key,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE records SET date_last_seen = ?, deadline = ? WHERE dedup_key = ?",
                    (today, r.deadline, key),
                )
            else:
                conn.execute(
                    """INSERT INTO records
                    (dedup_key, title, url, source, country, category, buyer, deadline,
                     value_estimate, keywords_matched, reason, date_first_seen, date_last_seen, expired)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (key, r.title, r.url, r.source, r.country, r.category, r.buyer, r.deadline,
                     r.value_estimate, ",".join(r.keywords_matched), r.reason, today, today),
                )
                new_records.append(r)
        # mark expired tenders whose deadline has passed
        conn.execute(
            "UPDATE records SET expired = 1 WHERE category = 'tender' AND deadline IS NOT NULL AND deadline < ?",
            (today,),
        )
    return new_records


def all_records():
    with connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM records ORDER BY date_first_seen DESC").fetchall()
        return [dict(r) for r in rows]
