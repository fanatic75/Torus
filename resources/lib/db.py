"""Local SQLite state — resume positions and Continue Watching.

Keyed on IMDb id (+ season/episode), never on the torrent hash, so a different
cached release next time still resumes at the right spot. Stores name/poster too
so the Continue Watching row renders without extra metadata calls.
"""

from __future__ import annotations
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            imdb TEXT PRIMARY KEY,
            mtype TEXT,
            name TEXT DEFAULT '',
            poster TEXT DEFAULT '',
            added_at INTEGER
        )
    """)
    # Custom folders for My List. A watchlist row's folder_id is NULL = root
    # (top level); an integer references folders.id. Movies and shows both allowed.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    try:  # migrate older DBs that predate folders
        conn.execute("ALTER TABLE watchlist ADD COLUMN folder_id INTEGER")
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


# --- watchlist -------------------------------------------------------------
def add_watchlist(imdb, mtype, name="", poster="", folder_id=None) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO watchlist (imdb, mtype, name, poster, folder_id, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (imdb, mtype, name, poster, folder_id, int(time.time())))
        conn.commit()
    finally:
        conn.close()


# --- watchlist folders -----------------------------------------------------
def _folder_id_by_name(conn, name):
    row = conn.execute("SELECT id FROM folders WHERE name=? COLLATE NOCASE",
                       (name,)).fetchone()
    return row[0] if row else None


def create_folder(name) -> int | None:
    """Create a folder and return its id, or return the id of an existing folder
    with the same name (case-insensitive) so names don't duplicate. Returns None
    if the name is blank after trimming."""
    name = (name or "").strip()
    if not name:
        return None
    conn = _connect()
    try:
        existing = _folder_id_by_name(conn, name)
        if existing is not None:
            return existing
        cur = conn.execute("INSERT INTO folders (name, created_at) VALUES (?, ?)",
                           (name, int(time.time())))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def rename_folder(folder_id, name) -> bool:
    """Rename a folder. Returns False if the name is blank or already used by a
    different folder (case-insensitive)."""
    name = (name or "").strip()
    if not name:
        return False
    conn = _connect()
    try:
        other = _folder_id_by_name(conn, name)
        if other is not None and other != folder_id:
            return False
        conn.execute("UPDATE folders SET name=? WHERE id=?", (name, folder_id))
        conn.commit()
        return True
    finally:
        conn.close()


def list_folders() -> list[dict]:
    """All custom folders with their item counts, alphabetical."""
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT f.id, f.name, COUNT(w.imdb) AS count
            FROM folders f
            LEFT JOIN watchlist w ON w.folder_id = f.id
            GROUP BY f.id, f.name
            ORDER BY f.name COLLATE NOCASE
        """).fetchall()
    finally:
        conn.close()
    return [dict(zip(("id", "name", "count"), r)) for r in rows]


def get_folder(folder_id) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT id, name FROM folders WHERE id=?", (folder_id,)).fetchone()
    finally:
        conn.close()
    return {"id": row[0], "name": row[1]} if row else None


def delete_folder(folder_id) -> None:
    """Delete a folder AND every title inside it (destructive, per design)."""
    conn = _connect()
    try:
        conn.execute("DELETE FROM watchlist WHERE folder_id=?", (folder_id,))
        conn.execute("DELETE FROM folders WHERE id=?", (folder_id,))
        conn.commit()
    finally:
        conn.close()


def move_to_folder(imdb, folder_id) -> None:
    """Move a watchlist title to a folder (folder_id None = back to root)."""
    conn = _connect()
    try:
        conn.execute("UPDATE watchlist SET folder_id=? WHERE imdb=?", (folder_id, imdb))
        conn.commit()
    finally:
        conn.close()


def remove_watchlist(imdb) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM watchlist WHERE imdb=?", (imdb,))
        conn.commit()
    finally:
        conn.close()


def in_watchlist(imdb) -> bool:
    conn = _connect()
    try:
        return conn.execute("SELECT 1 FROM watchlist WHERE imdb=?", (imdb,)).fetchone() is not None
    finally:
        conn.close()


def watchlist_ids() -> set:
    conn = _connect()
    try:
        return {r[0] for r in conn.execute("SELECT imdb FROM watchlist").fetchall()}
    finally:
        conn.close()


def list_watchlist(folder_id=None, limit=300) -> list[dict]:
    """Titles in a folder. folder_id None = root (top-level, un-foldered) items."""
    conn = _connect()
    try:
        if folder_id is None:
            rows = conn.execute(
                "SELECT imdb, mtype, name, poster FROM watchlist "
                "WHERE folder_id IS NULL ORDER BY added_at DESC LIMIT ?",
                (limit,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT imdb, mtype, name, poster FROM watchlist "
                "WHERE folder_id=? ORDER BY added_at DESC LIMIT ?",
                (folder_id, limit)).fetchall()
    finally:
        conn.close()
    return [dict(zip(("imdb", "mtype", "name", "poster"), r)) for r in rows]


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
        # One entry per title (imdb): the most-recently-watched episode/movie that
        # isn't effectively finished, plus any queued "next up".
        rows = conn.execute("""
            SELECT imdb, mtype, season, episode, position, duration, name, poster, nextup
            FROM progress p
            WHERE (nextup = 1 OR (duration > 0 AND (position / duration) < 0.95))
              AND updated_at = (
                  SELECT MAX(updated_at) FROM progress p2
                  WHERE p2.imdb = p.imdb
                    AND (p2.nextup = 1 OR (p2.duration > 0 AND (p2.position / p2.duration) < 0.95))
              )
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
    finally:
        conn.close()
    keys = ("imdb", "mtype", "season", "episode", "position", "duration",
            "name", "poster", "nextup")
    return [dict(zip(keys, row)) for row in rows]
