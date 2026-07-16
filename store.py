"""Comment storage.

Comments are keyed on the article URL rather than on a cluster. Clusters are
recomputed from live feeds every time and are not stable across runs; the
article URL is. Normalising the URL (see common_story.normalise_url) is what
makes that key hold -- Scroll appends ?utm_source=rss and NDTV appends #pfrom=
fragments, so the raw link differs between fetches of the same article.
"""

import pathlib
import sqlite3

DB_PATH = pathlib.Path(__file__).parent / "single.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS comments (
    url        TEXT PRIMARY KEY,
    source     TEXT NOT NULL,
    headline   TEXT NOT NULL,
    comment    TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    with connect() as conn:
        conn.executescript(SCHEMA)


def save_comment(url, source, headline, comment):
    """Write a comment, or clear it if the text is blank."""
    with connect() as conn:
        if not comment.strip():
            conn.execute("DELETE FROM comments WHERE url = ?", (url,))
        else:
            conn.execute(
                """INSERT INTO comments (url, source, headline, comment, updated_at)
                   VALUES (?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(url) DO UPDATE SET
                       comment = excluded.comment,
                       updated_at = excluded.updated_at""",
                (url, source, headline, comment.strip()),
            )


def comments_for(urls):
    if not urls:
        return {}
    placeholders = ",".join("?" * len(urls))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT url, comment FROM comments WHERE url IN ({placeholders})",
            list(urls),
        ).fetchall()
    return {row["url"]: row["comment"] for row in rows}


def all_comments():
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM comments ORDER BY updated_at DESC"
        ).fetchall()


def count():
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM comments").fetchone()["n"]
