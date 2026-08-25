"""Local SQLite state — resume positions and Continue Watching.

Keyed on IMDb id (+ season/episode), never on the torrent hash, so a different
cached release next time still resumes at the right spot. Stores name/poster too
so the Continue Watching row renders without extra metadata calls.
"""
import os
import sqlite3
import time

from . import config


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(os.path.join(config.profile_dir(), "state.db"), timeout=5)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            imdb TEXT NOT NULL,
            mtype TEXT NOT NULL,
            season INTEGER NOT NULL DEFAULT 0,
            episode INTEGER NOT NULL DEFAULT 0,
            position REAL NOT NULL,
            duration REAL NOT NULL,
            name TEXT DEFAULT '',
            poster TEXT DEFAULT '',
            url TEXT DEFAULT '',
            nextup INTEGER DEFAULT 0,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (imdb, season, episode)
        )
    """)
    # Migrate older DBs that predate newer columns.
    for column, ddl in (("url", "url TEXT DEFAULT ''"),
                        ("nextup", "nextup INTEGER DEFAULT 0")):
        try:
            conn.execute(f"ALTER TABLE progress ADD COLUMN {ddl}")
        except sqlite3.OperationalError:
            pass
    return conn


def save_progress(imdb, mtype, season, episode, position, duration,
                  name="", poster="", url="") -> None:
    season, episode = int(season or 0), int(episode or 0)
    conn = _connect()
    try:
        conn.execute("""
            INSERT INTO progress
                (imdb, mtype, season, episode, position, duration, name, poster, url, nextup, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(imdb, season, episode) DO UPDATE SET
                position=excluded.position,
                duration=excluded.duration,
                mtype=excluded.mtype,
                name=COALESCE(NULLIF(excluded.name, ''), progress.name),
                poster=COALESCE(NULLIF(excluded.poster, ''), progress.poster),
                url=COALESCE(NULLIF(excluded.url, ''), progress.url),
                nextup=0,
                updated_at=excluded.updated_at
        """, (imdb, mtype, season, episode, position, duration, name, poster, url,
              int(time.time())))
        conn.commit()
    finally:
        conn.close()


def set_next_up(imdb, mtype, season, episode, name="", poster="") -> None:
    """Queue the next episode of a series in Continue Watching (not yet started)."""
    season, episode = int(season or 0), int(episode or 0)
    conn = _connect()
    try:
        conn.execute("""
            INSERT INTO progress
                (imdb, mtype, season, episode, position, duration, name, poster, url, nextup, updated_at)
            VALUES (?, ?, ?, ?, 0, 0, ?, ?, '', 1, ?)
            ON CONFLICT(imdb, season, episode) DO UPDATE SET
                nextup=1, position=0, duration=0,
                name=COALESCE(NULLIF(excluded.name, ''), progress.name),
                poster=COALESCE(NULLIF(excluded.poster, ''), progress.poster),
                updated_at=excluded.updated_at
        """, (imdb, mtype, season, episode, name, poster, int(time.time())))
        conn.commit()
    finally:
        conn.close()


def get_progress(imdb, season=0, episode=0) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT position, duration, url FROM progress WHERE imdb=? AND season=? AND episode=?",
            (imdb, int(season or 0), int(episode or 0)),
        ).fetchone()
    finally:
        conn.close()
    return {"position": row[0], "duration": row[1], "url": row[2]} if row else None


def clear_progress(imdb, season=0, episode=0) -> None:
    conn = _connect()
    try:
        conn.execute(
            "DELETE FROM progress WHERE imdb=? AND season=? AND episode=?",
            (imdb, int(season or 0), int(episode or 0)),
        )
        conn.commit()
    finally:
        conn.close()


RETENTION_DAYS = 365


def prune(max_age_days: int = RETENTION_DAYS) -> int:
    """Drop resume points not touched in a long time (abandoned watches).

    The table is tiny (~0.3 KB/row), so this is hygiene, not a space necessity.
    Returns the number of rows removed.
    """
    cutoff = int(time.time()) - max_age_days * 86400
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM progress WHERE updated_at < ?", (cutoff,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def list_continue(limit=40) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT imdb, mtype, season, episode, position, duration, name, poster, nextup
            FROM progress
            WHERE nextup = 1
               OR (duration > 0 AND (position / duration) BETWEEN 0.02 AND 0.9)
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
    finally:
        conn.close()
    keys = ("imdb", "mtype", "season", "episode", "position", "duration",
            "name", "poster", "nextup")
    return [dict(zip(keys, row)) for row in rows]
