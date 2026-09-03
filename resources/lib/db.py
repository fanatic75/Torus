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
    # Best-effort migrations for older DBs. Each ALTER is independent so a column
    # that already exists (OperationalError) doesn't block the others.
    for stmt in (
        "ALTER TABLE watchlist ADD COLUMN folder_id INTEGER",
        # pinned titles float to the top of their container; position is the
        # manual order (lower = higher up) set by grab-and-place reordering.
        "ALTER TABLE watchlist ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE watchlist ADD COLUMN position INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE folders ADD COLUMN position INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE folders ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0",
    ):
        try:
            conn.execute(stmt)
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
def _anchored_insert(entries, new_entry):
    """Place `new_entry` as the topmost UNPINNED slot while every pinned entry
    keeps its exact index. `entries` is the current display order (each a dict
    with a truthy/falsy 'pinned'); returns the new ordered list. This is how a
    freshly-added title lands at the top without shoving pinned items down."""
    n = len(entries)
    pinned_at = {i: e for i, e in enumerate(entries) if e.get("pinned")}
    flow = [new_entry] + [e for e in entries if not e.get("pinned")]
    result, fi = [None] * (n + 1), 0
    for i in range(n + 1):
        if i in pinned_at:
            result[i] = pinned_at[i]
        else:
            result[i] = flow[fi]
            fi += 1
    return result


def add_watchlist(imdb, mtype, name="", poster="", folder_id=None) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO watchlist "
            "(imdb, mtype, name, poster, folder_id, pinned, position, added_at) "
            "VALUES (?, ?, ?, ?, ?, 0, 0, ?)",
            (imdb, mtype, name, poster, folder_id, int(time.time())))
        conn.commit()
    finally:
        conn.close()
    _place_new_on_top(imdb, folder_id)


def _place_root_key_on_top(key) -> None:
    """Insert a root entry key ('t:<imdb>' or 'f:<id>') as the topmost unpinned
    slot in the unified root order, pinned entries anchored."""
    entries = [e for e in list_root_entries() if e.get("key") != key]
    ordered = _anchored_insert(entries, {"key": key, "pinned": 0})
    set_root_order([e["key"] for e in ordered])


def _place_new_on_top(imdb, folder_id) -> None:
    """Re-lay the container so the just-added `imdb` is the topmost unpinned
    entry, pinned entries anchored. Root = folders + titles interleaved; inside a
    folder = titles only."""
    if folder_id is None:
        _place_root_key_on_top(f"t:{imdb}")
    else:
        entries = [r for r in list_watchlist(folder_id) if r["imdb"] != imdb]
        ordered = _anchored_insert(entries, {"imdb": imdb, "pinned": 0})
        set_watchlist_order([e["imdb"] for e in ordered])


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
        cur = conn.execute(
            "INSERT INTO folders (name, created_at, position, pinned) VALUES (?, ?, 0, 0)",
            (name, int(time.time())))
        conn.commit()
        fid = cur.lastrowid
    finally:
        conn.close()
    _place_root_key_on_top(f"f:{fid}")  # new folder joins the unified order at top
    return fid


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
            SELECT f.id, f.name, COUNT(w.imdb) AS count, f.pinned, f.position
            FROM folders f
            LEFT JOIN watchlist w ON w.folder_id = f.id
            GROUP BY f.id, f.name
            ORDER BY f.position ASC, f.name COLLATE NOCASE
        """).fetchall()
    finally:
        conn.close()
    return [dict(zip(("id", "name", "count", "pinned", "position"), r)) for r in rows]


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
    _place_new_on_top(imdb, folder_id)  # lands at the top of its new container


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
    """Titles in a folder, in the user's manual order. folder_id None = root
    (top-level, un-foldered) items. Pins do NOT float — they hold their slot
    (see _anchored_insert); the flag is returned only for the 📌 badge."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT imdb, mtype, name, poster, pinned FROM watchlist "
            "WHERE folder_id IS ? "
            "ORDER BY position ASC, added_at DESC LIMIT ?",
            (folder_id, limit)).fetchall()
    finally:
        conn.close()
    return [dict(zip(("imdb", "mtype", "name", "poster", "pinned"), r)) for r in rows]


def list_root_entries() -> list[dict]:
    """The unified My List root: custom folders AND un-foldered titles merged
    into one user-ordered sequence (a folder can sit between two titles). Each
    entry carries a 'kind' ('folder'|'title'), a 'key' ('f:<id>'/'t:<imdb>'),
    'pinned', and 'position'."""
    conn = _connect()
    try:
        frows = conn.execute("""
            SELECT f.id, f.name, COUNT(w.imdb) AS count, f.pinned, f.position, f.created_at
            FROM folders f LEFT JOIN watchlist w ON w.folder_id = f.id
            GROUP BY f.id, f.name
        """).fetchall()
        trows = conn.execute(
            "SELECT imdb, mtype, name, poster, pinned, position, added_at "
            "FROM watchlist WHERE folder_id IS NULL").fetchall()
    finally:
        conn.close()
    entries = []
    for r in frows:
        entries.append({"kind": "folder", "key": f"f:{r[0]}", "id": r[0], "name": r[1],
                        "count": r[2], "pinned": r[3], "position": r[4], "_t": r[5] or 0})
    for r in trows:
        entries.append({"kind": "title", "key": f"t:{r[0]}", "imdb": r[0], "mtype": r[1],
                        "name": r[2], "poster": r[3], "pinned": r[4], "position": r[5],
                        "_t": r[6] or 0})
    # position is the primary order; the tiebreak only matters before the first
    # reorder (fresh/migrated rows share position 0): folders first, then newest.
    entries.sort(key=lambda e: (e["position"],
                                0 if e["kind"] == "folder" else 1,
                                -e["_t"]))
    for e in entries:
        e.pop("_t", None)
    return entries


def set_root_order(ordered_keys) -> None:
    """Assign positions 0..n across the merged root, writing each key back to its
    own table ('f:<id>' → folders, 't:<imdb>' → watchlist)."""
    conn = _connect()
    try:
        for i, key in enumerate(ordered_keys):
            kind, _, ident = key.partition(":")
            if kind == "f":
                conn.execute("UPDATE folders SET position=? WHERE id=?", (i, int(ident)))
            else:
                conn.execute("UPDATE watchlist SET position=? WHERE imdb=?", (i, ident))
        conn.commit()
    finally:
        conn.close()


def set_pinned(imdb, pinned: bool) -> None:
    """Pin/unpin a watchlist title. Pinning anchors it in place (see
    _anchored_insert); it does not move the item."""
    conn = _connect()
    try:
        conn.execute("UPDATE watchlist SET pinned=? WHERE imdb=?",
                     (1 if pinned else 0, imdb))
        conn.commit()
    finally:
        conn.close()


def is_pinned(imdb) -> bool:
    conn = _connect()
    try:
        row = conn.execute("SELECT pinned FROM watchlist WHERE imdb=?", (imdb,)).fetchone()
    finally:
        conn.close()
    return bool(row and row[0])


def set_folder_pinned(folder_id, pinned: bool) -> None:
    """Pin/unpin a folder (anchors it in the unified root order)."""
    conn = _connect()
    try:
        conn.execute("UPDATE folders SET pinned=? WHERE id=?",
                     (1 if pinned else 0, int(folder_id)))
        conn.commit()
    finally:
        conn.close()


def is_folder_pinned(folder_id) -> bool:
    conn = _connect()
    try:
        row = conn.execute("SELECT pinned FROM folders WHERE id=?", (int(folder_id),)).fetchone()
    finally:
        conn.close()
    return bool(row and row[0])


def set_watchlist_order(ordered_imdbs) -> None:
    """Assign positions 0..n to the given titles, in the order provided."""
    conn = _connect()
    try:
        for i, imdb in enumerate(ordered_imdbs):
            conn.execute("UPDATE watchlist SET position=? WHERE imdb=?", (i, imdb))
        conn.commit()
    finally:
        conn.close()


def set_folder_order(ordered_ids) -> None:
    """Assign positions 0..n to the given folders, in the order provided."""
    conn = _connect()
    try:
        for i, fid in enumerate(ordered_ids):
            conn.execute("UPDATE folders SET position=? WHERE id=?", (i, int(fid)))
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
