"""SQLite store for TV segments and their comments.

Transcripts are slow to fetch (one scrape per video, minutes for a week's
worth), so they are cached here rather than pulled per page load. The cache is
also what makes the tool work at all: a live feed is one snapshot, and a week
of accumulated rows is what gives a story enough time to be picked up by
several channels.

Comments are keyed on video_id, which is stable. Clusters are recomputed every
run and are not.
"""

import pathlib
import sqlite3

DB_PATH = pathlib.Path(__file__).parent / "single.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id    TEXT PRIMARY KEY,
    channel     TEXT NOT NULL,
    title       TEXT NOT NULL,
    published   TEXT NOT NULL,          -- ISO8601 UTC
    url         TEXT NOT NULL,
    is_live     INTEGER NOT NULL,       -- live streams carry no captions
    transcript  TEXT,                   -- NULL = untried, '' = unavailable
    fetched_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS videos_published ON videos(published);

CREATE TABLE IF NOT EXISTS comments (
    video_id   TEXT PRIMARY KEY,
    channel    TEXT NOT NULL,
    title      TEXT NOT NULL,
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


def upsert_video(video_id, channel, title, published, url, is_live):
    """Insert a video, leaving any transcript already fetched intact."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO videos (video_id, channel, title, published, url, is_live)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(video_id) DO UPDATE SET
                   title = excluded.title,
                   is_live = excluded.is_live""",
            (video_id, channel, title, published, url, int(is_live)),
        )


def set_transcript(video_id, text):
    """Store a transcript. '' records that we tried and it is unavailable,
    which stops us retrying it forever on every run."""
    with connect() as conn:
        conn.execute("UPDATE videos SET transcript = ? WHERE video_id = ?",
                     (text, video_id))


def needing_transcript(limit=500):
    """Non-live videos not yet tried."""
    with connect() as conn:
        return conn.execute(
            """SELECT video_id, channel FROM videos
               WHERE transcript IS NULL AND is_live = 0
               ORDER BY published DESC LIMIT ?""", (limit,)
        ).fetchall()


def segments_since(days=7):
    """Non-live videos in the window that have a usable transcript."""
    with connect() as conn:
        return conn.execute(
            """SELECT * FROM videos
               WHERE is_live = 0
                 AND transcript IS NOT NULL AND transcript != ''
                 AND published >= datetime('now', ?)
               ORDER BY published DESC""", (f"-{days} days",)
        ).fetchall()


def save_comment(video_id, channel, title, comment):
    with connect() as conn:
        if not comment.strip():
            conn.execute("DELETE FROM comments WHERE video_id = ?", (video_id,))
        else:
            conn.execute(
                """INSERT INTO comments (video_id, channel, title, comment, updated_at)
                   VALUES (?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(video_id) DO UPDATE SET
                       comment = excluded.comment,
                       updated_at = excluded.updated_at""",
                (video_id, channel, title, comment.strip()),
            )


def comments_for(video_ids):
    if not video_ids:
        return {}
    marks = ",".join("?" * len(video_ids))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT video_id, comment FROM comments WHERE video_id IN ({marks})",
            list(video_ids)).fetchall()
    return {r["video_id"]: r["comment"] for r in rows}


def stats():
    with connect() as conn:
        return dict(conn.execute(
            """SELECT
                 (SELECT COUNT(*) FROM videos)                        AS videos,
                 (SELECT COUNT(*) FROM videos WHERE is_live = 1)      AS live,
                 (SELECT COUNT(*) FROM videos WHERE transcript IS NULL
                                                AND is_live = 0)      AS pending,
                 (SELECT COUNT(*) FROM videos WHERE transcript = '')  AS unavailable,
                 (SELECT COUNT(*) FROM videos WHERE transcript IS NOT NULL
                                                AND transcript != '') AS usable,
                 (SELECT COUNT(DISTINCT channel) FROM videos)         AS channels,
                 (SELECT COUNT(*) FROM comments)                      AS comments
            """).fetchone())
