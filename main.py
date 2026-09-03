"""Torus plugin entry point (router).

Kodi invokes this file for every navigation action with three argv values:
    argv[0] -> base plugin url, e.g. "plugin://plugin.video.torus/"
    argv[1] -> the integer handle Kodi expects us to fill with a directory
    argv[2] -> the query string, e.g. "?action=catalog&mtype=movie&cat=top"

Stateless request/response: parse the action, build a listing, endOfDirectory,
exit. Metaadta is Cinemeta (keyless, IMDb-keyed); sources come from the provider
layer (Comet) and play via setResolvedUrl.
"""

from __future__ import annotations
import json
import sys
from urllib.parse import urlencode, parse_qsl

import xbmc
import xbmcgui
import xbmcplugin

from resources.lib import auth, cinemeta, config, db, providers, ranking, release_groups, torbox
from resources.lib.http import HttpError, log
from resources.lib.kodi import listing

PLAYING_PROP = "torus.playing"
# Grab-and-place reorder state: the currently "grabbed" My List entry, as a
# window property so it survives the stateless plugin re-invocations. Value is
# "t:<imdb>" for a title or "f:<folder_id>" for a folder; empty = nothing grabbed.
REORDER_PROP = "torus.reorder.grab"
# Rewind a few seconds on resume so it's easy to pick up where you left off.
RESUME_REWIND = 10

# argv is a real plugin invocation only when Kodi launches us. Guard it so the
# module stays importable under tests (HANDLE falls back to -1, a no-op handle).
BASE_URL = sys.argv[0] if sys.argv and sys.argv[0].startswith("plugin://") else "plugin://plugin.video.torus/"
try:
    HANDLE = int(sys.argv[1])
except (IndexError, ValueError):
    HANDLE = -1


# --- helpers ---------------------------------------------------------------
def build_url(**kwargs) -> str:
    return f"{BASE_URL}?{urlencode(kwargs)}"


def add_directory(label: str, action: str, **extra) -> None:
    item = xbmcgui.ListItem(label=label)
    item.setArt({"icon": "DefaultFolder.png"})
    xbmcplugin.addDirectoryItem(HANDLE, build_url(action=action, **extra), item, isFolder=True)


def add_item(item: xbmcgui.ListItem, is_folder: bool, **params) -> None:
    xbmcplugin.addDirectoryItem(HANDLE, build_url(**params), item, isFolder=is_folder)


def finish(content: str | None = None) -> None:
    if content:
        xbmcplugin.setContent(HANDLE, content)
    xbmcplugin.endOfDirectory(HANDLE)


def notify(message: str) -> None:
    xbmcgui.Dialog().notification("Torus", message, xbmcgui.NOTIFICATION_WARNING)


# --- menus -----------------------------------------------------------------
def home() -> None:
    linked = bool(config.torbox_token())
    if not linked:
        link = xbmcgui.ListItem(label="🔗  Link your TorBox account")
        link.setArt({"icon": "DefaultAddonService.png"})
        xbmcplugin.addDirectoryItem(HANDLE, build_url(action="auth_torbox"), link, isFolder=False)
    add_directory("Movies", "menu", mtype="movie")
    add_directory("TV Shows", "menu", mtype="series")
    add_directory("Search", "search_menu")
    add_directory("Continue Watching", "continue")
    add_directory("My List", "watchlist")
    if linked:
        add_directory("☁  TorBox Cloud", "torbox_list")
        # No liveness check — "linked" is just token presence — so always offer a
        # relink to recover from an expired/revoked token or to switch accounts.
        # Same device-code dialog as first-time Link (shows URL + PIN);
        # run_device_auth() overwrites the stored token, only on success.
        relink = xbmcgui.ListItem(label="🔗  Relink TorBox account")
        relink.setArt({"icon": "DefaultAddonService.png"})
        xbmcplugin.addDirectoryItem(HANDLE, build_url(action="auth_torbox"), relink, isFolder=False)
    finish()


def menu(mtype: str) -> None:
    add_directory("Popular", "catalog", mtype=mtype, cat="top")
    add_directory("Top Rated", "catalog", mtype=mtype, cat="imdbRating")
    add_directory("New", "catalog", mtype=mtype, cat="year")
    add_directory("Search", "search", mtype=mtype)
    finish()


def search_menu() -> None:
    add_directory("Search Movies", "search", mtype="movie")
    add_directory("Search TV Shows", "search", mtype="series")
    finish()


# --- catalogs + search -----------------------------------------------------
def _render(mtype: str, metas: list) -> None:
    watchlisted = db.watchlist_ids()
    for meta in metas:
        imdb = meta.get("id") or meta.get("imdb_id")
        if not imdb:
            continue
        item = listing.catalog_item(meta)
        item.addContextMenuItems(
            _watchlist_ctx(imdb, mtype, meta.get("name", ""), meta.get("poster", ""),
                           imdb in watchlisted))
        add_item(item, True, action="detail", imdb=imdb, mtype=mtype)
    finish("movies" if mtype == "movie" else "tvshows")


def catalog(mtype: str, cat: str) -> None:
    _render(mtype, cinemeta.catalog(mtype, cat))


def search(mtype: str) -> None:
    query = xbmcgui.Dialog().input("Search", type=xbmcgui.INPUT_ALPHANUM)
    if not query:
        finish()
        return
    _render(mtype, cinemeta.catalog(mtype, "top", search=query))


# --- detail ----------------------------------------------------------------
def _choose_source_ctx(imdb, mtype, season_number=0, episode_number=0):
    """Context-menu entry that opens the full ranked source list."""
    url = build_url(action="sources", imdb=imdb, mtype=mtype,
                    season=season_number, episode=episode_number)
    return [("Choose source", f"Container.Update({url})")]


def _watchlist_ctx(imdb, mtype, name, poster, in_list):
    """Context-menu entries to add/move/remove a title in My List."""
    if in_list:
        return [
            ("Move to folder…", f"RunPlugin({build_url(action='wl_move', imdb=imdb)})"),
            ("Remove from My List", f"RunPlugin({build_url(action='wl_remove', imdb=imdb)})"),
        ]
    return [("Add to My List",
             f"RunPlugin({build_url(action='wl_add', imdb=imdb, mtype=mtype, name=name, poster=poster)})")]


def _add_watchlist_toggle(imdb, mtype, meta):
    """Visible Add/Remove My List item for a detail page."""
    in_list = db.in_watchlist(imdb)
    item = xbmcgui.ListItem(
        label="★  Remove from My List" if in_list else "☆  Add to My List")
    add_item(item, False, action="wl_remove" if in_list else "wl_add",
             imdb=imdb, mtype=mtype, name=meta.get("name", ""), poster=meta.get("poster", ""))


def detail(imdb: str, mtype: str) -> None:
    meta = cinemeta.meta(mtype, imdb)
    if mtype == "movie":
        play_item = listing.catalog_item(meta)
        play_item.setLabel(f"▶  Play — {meta.get('name', '')}")
        play_item.setProperty("IsPlayable", "true")
        play_item.addContextMenuItems(_choose_source_ctx(imdb, "movie"))
        add_item(play_item, False, action="play", imdb=imdb, mtype="movie")
        # Explicit source picker too.
        choose = xbmcgui.ListItem(label="☰  Choose source")
        add_item(choose, True, action="sources", imdb=imdb, mtype="movie")
        _add_watchlist_toggle(imdb, "movie", meta)
        finish("movies")
        return
    # series: list seasons derived from the episode videos
    _add_watchlist_toggle(imdb, "series", meta)
    seasons = sorted({
        v.get("season", 0) for v in meta.get("videos", [])
        if v.get("season", 0) and v.get("season", 0) > 0
    })
    for season_number in seasons:
        add_item(listing.season_item(meta, season_number), True,
                 action="season", imdb=imdb, season=season_number)
    finish("seasons")


def season(imdb: str, season_number: int) -> None:
    meta = cinemeta.meta("series", imdb)
    episodes = sorted(
        (v for v in meta.get("videos", []) if v.get("season") == season_number),
        key=lambda v: v.get("episode", 0),
    )
    for video in episodes:
        episode_number = video.get("episode", 0)
        item = listing.episode_item(meta, video)
        item.addContextMenuItems(
            _choose_source_ctx(imdb, "series", season_number, episode_number))
        add_item(item, True, action="episode", imdb=imdb,
                 season=season_number, episode=episode_number)
    finish("episodes")


def episode(imdb: str, season_number: int, episode_number: int) -> None:
    """Per-episode actions: one-click Play (best source) + Choose source."""
    meta = cinemeta.meta("series", imdb)
    video = next((v for v in meta.get("videos", [])
                  if v.get("season") == season_number and v.get("episode") == episode_number), {})
    tag_line = f"S{season_number:02d}E{episode_number:02d}"
    title = video.get("name", "")

    play = listing.episode_item(meta, video) if video else xbmcgui.ListItem(label="Play")
    play.setLabel(f"▶  Play — {tag_line}" + (f"  {title}" if title else ""))
    play.setProperty("IsPlayable", "true")
    add_item(play, False, action="play", imdb=imdb, mtype="series",
             season=season_number, episode=episode_number)

    choose = xbmcgui.ListItem(label="☰  Choose source")
    add_item(choose, True, action="sources", imdb=imdb, mtype="series",
             season=season_number, episode=episode_number)
    finish()


def continue_watching() -> None:
    for row in db.list_continue():
        poster = row.get("poster") or ""
        label = row.get("name") or row["imdb"]
        if row.get("mtype") == "series" and row.get("episode"):
            label = f"{label}  S{row['season']:02d}E{row['episode']:02d}"
        if row.get("nextup"):
            label = f"▶ Up Next — {label}"
        item = xbmcgui.ListItem(label=label)
        item.setArt({"poster": poster, "thumb": poster})
        # Not IsPlayable: a click opens the Play / Choose source popover (cw_menu)
        # rather than resolving a stream straight away.
        tag = item.getVideoInfoTag()
        tag.setMediaType("movie" if row.get("mtype") == "movie" else "episode")
        tag.setTitle(row.get("name") or "")
        item.addContextMenuItems(_choose_source_ctx(
            row["imdb"], row.get("mtype", "movie"), row.get("season", 0), row.get("episode", 0)))
        add_item(item, False, action="cw_menu", imdb=row["imdb"], mtype=row.get("mtype", "movie"),
                 season=row.get("season", 0), episode=row.get("episode", 0))
    finish()


def cw_menu(imdb, mtype="movie", season_number=0, episode_number=0) -> None:
    """Popover for a Continue Watching row: Play (one-click resume of the best
    source) or Choose source (open the ranked source list; picking one resumes)."""
    choice = xbmcgui.Dialog().contextmenu(["▶  Play", "☰  Choose source"])
    if choice == 0:
        _play_via_playlist(imdb, mtype, season_number, episode_number)
    elif choice == 1:
        url = build_url(action="sources", imdb=imdb, mtype=mtype,
                        season=season_number, episode=episode_number)
        xbmc.executebuiltin(f"Container.Update({url})")
    if HANDLE >= 0:  # close the transient directory the click opened
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


def _play_via_playlist(imdb, mtype, season_number, episode_number) -> None:
    """Start playback through PLAYLIST_VIDEO (NOT PlayMedia).

    play() queues a lazy next-episode pointer into PLAYLIST_VIDEO so Kodi can
    autoplay the next episode at end. PlayMedia() plays a lone item *outside*
    that playlist, so the queued pointer never advances — which silently breaks
    autoplay-next for anything launched from the Continue Watching popover. We
    seed the playlist with the current episode and let play()'s 1-ahead chain
    take over from there."""
    url = build_url(action="play", imdb=imdb, mtype=mtype,
                    season=season_number, episode=episode_number)
    li = xbmcgui.ListItem(path=url)
    li.setProperty("IsPlayable", "true")
    pl = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
    pl.clear()  # drop any stale pointers from a previous show
    pl.add(url, li)
    xbmc.Player().play(pl)


# --- sources + playback ----------------------------------------------------
def sources(imdb: str, mtype: str, season_number=None, episode_number=None) -> None:
    if not imdb:
        notify("No IMDb id found for this title")
        finish()
        return
    if not config.torbox_token():
        notify("Link your TorBox account first")
        finish()
        return

    expected = ""
    try:
        expected = cinemeta.meta(mtype, imdb).get("name", "")
    except Exception:  # noqa: BLE001 - matching is best-effort; keep listing all sources
        expected = ""
    provider = providers.get_provider()
    streams = ranking.rank(provider.search(imdb, mtype, season_number, episode_number),
                           expected=expected, series=(mtype == "series"))
    if not streams:
        notify("No cached sources found")

    for stream in streams:
        tier = release_groups.tier_label(stream.title)
        bits = [b for b in (stream.quality, stream.size, tier) if b]
        prefix = f"[{' · '.join(bits)}] " if bits else ""
        item = xbmcgui.ListItem(label=f"{prefix}{stream.title}")
        item.setProperty("IsPlayable", "true")
        tag = item.getVideoInfoTag()
        tag.setMediaType("movie" if mtype == "movie" else "episode")
        tag.setTitle(stream.title)
        add_item(item, False, action="play", url=stream.url, imdb=imdb, mtype=mtype,
                 season=season_number or 0, episode=episode_number or 0,
                 title=stream.title, quality=stream.quality, size=stream.size,
                 seeders=str(stream.seeders) if stream.seeders else "")
    finish()


FALLBACK_SOURCES = 3  # top-N sources kept for auto-retry when playback fails


def _resolve_ranked(imdb, mtype, season_number, episode_number, expected=""):
    """Ranked candidate Streams (best first) for the auto-pick paths. Match-aware
    (right show) and Torrentio-preferred (from the provider merge). The top one is
    played; the next few are kept as fallbacks the service auto-retries if the
    stream fails to open."""
    provider = providers.get_provider()
    return ranking.rank(
        provider.search(imdb, mtype, season_number or None, episode_number or None),
        expected=expected, series=(mtype == "series"))


def _played_base_item(meta, mtype, season_number, episode_number, url):
    """A rich ListItem for the resolved stream, carrying Cinemeta identity
    (title / plot / year / rating / genres / art), reusing the same builders as
    the browse pages. Falls back to a bare item when meta is unavailable."""
    if meta and mtype == "movie":
        item = listing.catalog_item(meta)
        item.getVideoInfoTag().setMediaType("movie")
    elif meta and mtype == "series":
        video = next((v for v in meta.get("videos", [])
                      if v.get("season") == season_number and v.get("episode") == episode_number), {})
        item = listing.episode_item(meta, video) if video else xbmcgui.ListItem()
    else:
        item = xbmcgui.ListItem()
    item.setPath(url)
    return item


def _apply_source_info(item, mtype, title="", quality="", size="", seeders="") -> None:
    """Append the source/release block (quality, size, TRaSH group tier, seeders,
    filename) to the item's plot, so Kodi's OSD "Information" shows WHICH release
    is playing alongside the Cinemeta synopsis. Cinemeta title/art are left intact."""
    tag = item.getVideoInfoTag()
    tag.setMediaType("movie" if mtype == "movie" else "episode")
    tier = release_groups.tier_label(title) if title else ""
    try:
        s = int(seeders)
    except (TypeError, ValueError):
        s = 0
    lines = []
    if quality:
        lines.append(f"Quality: {quality}")
    if size:
        lines.append(f"Size: {size}")
    if tier:
        lines.append(f"Group: {tier}")
    if s:
        lines.append(f"Seeders: {s}")
    if title:
        lines.append(title)
    if not lines:
        return
    block = "── Source ──\n" + "\n".join(lines)
    try:
        base = tag.getPlot()
    except Exception:  # noqa: BLE001 - older API without a getter
        base = ""
    tag.setPlot(f"{base}\n\n{block}" if base else block)


def _episode_pointer_item(nxt) -> tuple[str, xbmcgui.ListItem]:
    """A playable *plugin-URL* ListItem for a queued next episode.

    It points back at action=play, so the next episode's TorBox link is resolved
    only when Kodi actually advances to this item — nothing is pre-fetched.
    """
    url = build_url(action="play", imdb=nxt["imdb"], mtype="series",
                    season=nxt["season"], episode=nxt["episode"])
    label = "S%02dE%02d" % (nxt["season"], nxt["episode"])
    if nxt.get("name"):
        label += f"  {nxt['name']}"
    li = xbmcgui.ListItem(label=label)
    li.setProperty("IsPlayable", "true")
    if nxt.get("poster"):
        li.setArt({"poster": nxt["poster"], "thumb": nxt["poster"]})
    li.getVideoInfoTag().setMediaType("episode")
    return url, li


def _queue_next_episode(imdb, season_number, episode_number) -> None:
    """Queue ONE lazy next-episode pointer after the current stream so Kodi's
    native next-track control and autoplay-next work — without pre-queuing the
    season or pre-fetching any link.

    Called after the current episode has been resolved. play() re-runs when Kodi
    advances to the pointer, which resolves that episode and queues the one after
    it — an endless 1-ahead chain that only ever holds pointers, never streams.
    """
    nxt = cinemeta.next_episode(imdb, season_number, episode_number)
    if not nxt:
        return  # last episode — leave the ⏭ control inert, correctly
    pl = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
    pos = pl.getposition()  # NB: lowercase — PlayList.getposition(), not getPosition()
    # Drop anything still queued after the current item — a stale pointer from a
    # previous show, or this play()'s own earlier run — so exactly one follows.
    if pos >= 0:
        for i in range(len(pl) - 1, pos, -1):
            try:
                pl.remove(pl[i].getPath())
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
    url, li = _episode_pointer_item(nxt)
    if not any(pl[i].getPath() == url for i in range(len(pl))):
        pl.add(url, li)


def _folder_kw(folder_id):
    """URL kwargs for the current container: {} at root, else {'folder': id}."""
    return {} if folder_id is None else {"folder": folder_id}


def _add_watchlist_row(row) -> None:
    """Render one My List title (movie or show) as a browsable item."""
    meta_like = {"id": row["imdb"], "name": row["name"],
                 "type": row["mtype"], "poster": row["poster"]}
    item = listing.catalog_item(meta_like)
    if row.get("pinned"):  # pinned titles carry a badge (they hold their slot)
        item.setLabel(f"📌  {item.getLabel()}")
    add_item(item, True, action="detail", imdb=row["imdb"], mtype=row["mtype"])


def _add_folder_row(entry) -> None:
    """Render one custom folder row in the unified My List order."""
    label = f"📁  {entry['name']}  ({entry['count']})"
    if entry.get("pinned"):
        label = f"📌  {label}"
    item = xbmcgui.ListItem(label=label)
    item.setArt({"icon": "DefaultFolder.png"})
    add_item(item, True, action="wl_folder", folder=entry["id"])


def _options_button(folder_id) -> None:
    """A single OK-driven '⚙ Options' row — the one entry point for New folder /
    Reorder / Pin (and, inside a folder, Rename / Delete). Keeps a bare TV remote
    (no context menu) able to manage the list without cluttering it with buttons."""
    item = xbmcgui.ListItem(label="⚙  Options")
    item.setArt({"icon": "DefaultAddonProgram.png"})
    add_item(item, False, action="wl_options", **_folder_kw(folder_id))


def watchlist() -> None:
    """My List root: an Options row, then folders and titles in one unified order."""
    xbmcgui.Window(10000).clearProperty(REORDER_PROP)  # leaving any reorder session
    entries = db.list_root_entries()

    if not entries:
        nf = xbmcgui.ListItem(label="＋  New folder")
        nf.setArt({"icon": "DefaultAddSource.png"})
        add_item(nf, False, action="wl_newfolder")
        add_item(xbmcgui.ListItem(
            label="Your list is empty — add titles from any movie or show"),
            False, action="noop")
        finish()
        return

    _options_button(None)
    for e in entries:
        if e["kind"] == "folder":
            _add_folder_row(e)
        else:
            _add_watchlist_row(e)
    finish("movies")


def wl_folder(folder_id: int) -> None:
    """Contents of one custom folder."""
    xbmcgui.Window(10000).clearProperty(REORDER_PROP)  # leaving any reorder session
    _options_button(folder_id)
    rows = db.list_watchlist(folder_id)
    if not rows:
        add_item(xbmcgui.ListItem(label="Empty folder — add titles here, or move them in"),
                 False, action="noop")
        finish()
        return
    for row in rows:
        _add_watchlist_row(row)
    finish("movies")


def wl_options(folder_id=None) -> None:
    """The Options popover. Root: New folder / Reorder / Pin items. Inside a
    folder: Reorder / Pin items / Rename / Delete."""
    kw = _folder_kw(folder_id)
    if folder_id is None:
        labels = ["＋  New folder", "⇅  Reorder", "📌  Pin items"]
        keys = ["newfolder", "reorder", "pin"]
    else:
        labels = ["⇅  Reorder", "📌  Pin items", "✎  Rename folder", "🗑  Delete folder"]
        keys = ["reorder", "pin", "rename", "delete"]
    choice = xbmcgui.Dialog().contextmenu(labels)
    if not (0 <= choice < len(keys)):
        if HANDLE >= 0:
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return
    key = keys[choice]
    if key == "newfolder":
        wl_newfolder()
    elif key == "reorder":
        _go(build_url(action="wl_reorder", **kw))
    elif key == "pin":
        _go(build_url(action="wl_pinmode", **kw))
    elif key == "rename":
        wl_renamefolder(folder_id)
    elif key == "delete":
        _delete_folder_from_options(folder_id)


def _delete_folder_from_options(folder_id) -> None:
    """Delete the current folder (confirm), then return to the root — the folder
    view we're standing in no longer exists to refresh."""
    folder = db.get_folder(folder_id)
    if folder and xbmcgui.Dialog().yesno(
            "Delete folder", f"Delete “{folder['name']}” and its titles?",
            yeslabel="Delete", nolabel="Cancel"):
        db.delete_folder(folder_id)
        xbmcgui.Dialog().notification("Torus", "Folder deleted", xbmcgui.NOTIFICATION_INFO)
        _go(build_url(action="watchlist"))
    elif HANDLE >= 0:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


def _go(url) -> None:
    """Close the transient directory the click opened and navigate to `url`."""
    if HANDLE >= 0:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    xbmc.executebuiltin(f"Container.Update({url})")


# --- My List: grab-and-place reorder + pin (OK-remote friendly) ------------
def _reorder_entries(folder_id):
    """Ordered (key, label) entries for the reorder screen, in the SAME unified
    order as the list itself — folders and titles interleaved at root."""
    entries = []
    if folder_id is None:
        for e in db.list_root_entries():
            label = f"📁  {e['name']}" if e["kind"] == "folder" else (e["name"] or e["imdb"])
            if e.get("pinned"):
                label = f"📌  {label}"
            entries.append((e["key"], label))
    else:
        for row in db.list_watchlist(folder_id):
            label = row["name"] or row["imdb"]
            if row.get("pinned"):
                label = f"📌  {label}"
            entries.append((f"t:{row['imdb']}", label))
    return entries


def wl_reorder(folder_id=None) -> None:
    """Grab-and-place reorder screen. OK on an item grabs it; OK on another spot
    drops it there; OK on the grabbed item again cancels; ✓ Done exits."""
    kw = _folder_kw(folder_id)
    grabbed = xbmcgui.Window(10000).getProperty(REORDER_PROP)

    done = xbmcgui.ListItem(label="✓  Done reordering")
    add_item(done, False, action="wl_reorder_done", **kw)

    entries = _reorder_entries(folder_id)
    if not entries:
        add_item(xbmcgui.ListItem(label="Nothing to reorder"), False, action="noop")
        finish()
        return

    for key, name in entries:
        if not grabbed:  # nothing held yet → every row is grabbable
            item = xbmcgui.ListItem(label=f"≡  {name}")
            add_item(item, False, action="wl_grab", key=key, **kw)
        elif key == grabbed:  # the held item → re-select to cancel
            item = xbmcgui.ListItem(label=f"⇕  {name}   ‹ moving — pick a spot ›")
            add_item(item, False, action="wl_grabcancel", **kw)
        else:  # a drop target: place the held item before this row
            item = xbmcgui.ListItem(label=f"⇩  {name}")
            add_item(item, False, action="wl_drop", before=key, **kw)

    if grabbed:  # explicit tail target so you can drop at the very bottom
        add_item(xbmcgui.ListItem(label="⤓  Move to bottom"),
                 False, action="wl_drop", before="__bottom__", **kw)
    finish()


def wl_grab(key, folder_id=None) -> None:
    xbmcgui.Window(10000).setProperty(REORDER_PROP, key)
    _refresh_container()


def wl_grabcancel(folder_id=None) -> None:
    xbmcgui.Window(10000).clearProperty(REORDER_PROP)
    _refresh_container()


def wl_drop(before, folder_id=None) -> None:
    """Place the grabbed entry before `before` (a t:/f: key or __bottom__) in the
    unified order. Folders and titles reorder freely against each other at root."""
    grabbed = xbmcgui.Window(10000).getProperty(REORDER_PROP)
    if grabbed:
        if folder_id is None:  # unified root: folders + titles in one sequence
            order = [e["key"] for e in db.list_root_entries() if e["key"] != grabbed]
            order.insert(_drop_index(order, before), grabbed)
            db.set_root_order(order)
        else:  # inside a folder: titles only
            keys = [f"t:{r['imdb']}" for r in db.list_watchlist(folder_id)]
            order = [k for k in keys if k != grabbed]
            order.insert(_drop_index(order, before), grabbed)
            db.set_watchlist_order([k.partition(":")[2] for k in order])
    xbmcgui.Window(10000).clearProperty(REORDER_PROP)
    _refresh_container()


def _drop_index(order, before) -> int:
    """Insertion index into `order` (a list of keys) for a `before` key target;
    __bottom__ (or a missing target) appends at the end."""
    if before == "__bottom__":
        return len(order)
    return order.index(before) if before in order else len(order)


def wl_reorder_done(folder_id=None) -> None:
    xbmcgui.Window(10000).clearProperty(REORDER_PROP)
    _exit_manage_mode(folder_id)


# --- My List: pin mode -----------------------------------------------------
def wl_pinmode(folder_id=None) -> None:
    """Pin toggle screen: OK on an entry pins/unpins it. Pinning anchors an item
    to its current slot (it does NOT float to the top). Root lists folders +
    titles; a folder can be pinned too."""
    kw = _folder_kw(folder_id)
    add_item(xbmcgui.ListItem(label="✓  Done"), False, action="wl_pinmode_done", **kw)
    entries = _reorder_entries(folder_id)  # same unified order, same keys
    if not entries:
        add_item(xbmcgui.ListItem(label="Nothing here to pin"), False, action="noop")
        finish()
        return
    for key, label in entries:
        # _reorder_entries already prefixes a 📌 for pinned rows; show ☆ otherwise
        mark = "" if label.startswith("📌") else "☆  "
        item = xbmcgui.ListItem(label=f"{mark}{label}")
        add_item(item, False, action="wl_pintoggle", key=key, **kw)
    finish()


def wl_pintoggle(key, folder_id=None) -> None:
    kind, _, ident = key.partition(":")
    if kind == "f":
        db.set_folder_pinned(ident, not db.is_folder_pinned(ident))
    else:
        db.set_pinned(ident, not db.is_pinned(ident))
    _refresh_container()


def wl_pinmode_done(folder_id=None) -> None:
    _exit_manage_mode(folder_id)


def _refresh_container() -> None:
    """Re-render the current management screen in place (keeps the grab/pin state)."""
    if HANDLE >= 0:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    xbmc.executebuiltin("Container.Refresh")


def _exit_manage_mode(folder_id) -> None:
    """Leave a reorder/pin screen back to the normal My List view."""
    back = build_url(action="wl_folder", folder=folder_id) if folder_id is not None \
        else build_url(action="watchlist")
    if HANDLE >= 0:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    xbmc.executebuiltin(f"Container.Update({back},replace)")


def _after_watchlist_change() -> None:
    if HANDLE >= 0:  # a clicked item; RunPlugin context-menu passes handle -1
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    xbmc.executebuiltin("Container.Refresh")


def _pick_folder(heading: str):
    """Folder picker. Returns (chosen, folder_id): chosen=False if cancelled;
    folder_id None = root. Offers (No folder), New folder…, then existing folders."""
    folders = db.list_folders()
    options = ["(No folder)", "＋  New folder…"]
    ids = [None, "__new__"]
    for f in folders:
        options.append(f"{f['name']}  ({f['count']})")
        ids.append(f["id"])
    idx = xbmcgui.Dialog().select(heading, options)
    if idx < 0:
        return False, None
    choice = ids[idx]
    if choice == "__new__":
        name = xbmcgui.Dialog().input("New folder name", type=xbmcgui.INPUT_ALPHANUM)
        fid = db.create_folder(name)  # None if blank; reuses a same-name folder
        if fid is None:
            return False, None
        return True, fid
    return True, choice


def wl_add(imdb, mtype="movie", name="", poster="") -> None:
    chosen, folder_id = _pick_folder("Add to folder")
    if not chosen:
        _after_watchlist_change()
        return
    db.add_watchlist(imdb, mtype, name, poster, folder_id)
    xbmcgui.Dialog().notification("Torus", "Added to My List", xbmcgui.NOTIFICATION_INFO)
    _after_watchlist_change()


def wl_move(imdb) -> None:
    chosen, folder_id = _pick_folder("Move to folder")
    if not chosen:
        _after_watchlist_change()
        return
    db.move_to_folder(imdb, folder_id)
    xbmcgui.Dialog().notification("Torus", "Moved", xbmcgui.NOTIFICATION_INFO)
    _after_watchlist_change()


def wl_newfolder() -> None:
    name = xbmcgui.Dialog().input("New folder name", type=xbmcgui.INPUT_ALPHANUM)
    db.create_folder(name)  # no-ops on blank; reuses a same-name folder
    _after_watchlist_change()


def wl_renamefolder(folder_id: int) -> None:
    folder = db.get_folder(folder_id)
    if not folder:
        _after_watchlist_change()
        return
    name = xbmcgui.Dialog().input("Rename folder", folder["name"], type=xbmcgui.INPUT_ALPHANUM)
    if name and name.strip() != folder["name"]:
        if db.rename_folder(folder_id, name):
            xbmcgui.Dialog().notification("Torus", "Folder renamed", xbmcgui.NOTIFICATION_INFO)
        else:
            xbmcgui.Dialog().notification("Torus", "A folder with that name already exists",
                                          xbmcgui.NOTIFICATION_WARNING)
    _after_watchlist_change()


def wl_delfolder(folder_id: int) -> None:
    folder = db.get_folder(folder_id)
    if not folder:
        _after_watchlist_change()
        return
    n = len(db.list_watchlist(folder_id))
    msg = (f"Delete “{folder['name']}” and its {n} title(s)?" if n
           else f"Delete “{folder['name']}”?")
    if xbmcgui.Dialog().yesno("Delete folder", msg, yeslabel="Delete", nolabel="Cancel"):
        db.delete_folder(folder_id)
        xbmcgui.Dialog().notification("Torus", "Folder deleted", xbmcgui.NOTIFICATION_INFO)
    _after_watchlist_change()


def wl_remove(imdb) -> None:
    db.remove_watchlist(imdb)
    xbmcgui.Dialog().notification("Torus", "Removed from My List", xbmcgui.NOTIFICATION_INFO)
    _after_watchlist_change()


def _is_playlist_advance(imdb, mtype, season_number, episode_number) -> bool:
    """True when this play() is the video playlist advancing to the next-episode
    pointer we queued (⏭ / autoplay-next), rather than a fresh user pick."""
    if mtype != "series":
        return False
    pl = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
    pos = pl.getposition()
    # A genuine advance moves INTO this item from a previous one, so pos > 0.
    # A freshly-picked episode sits at position 0 of a new transient playlist
    # (its path also matches this_ptr) — that's a fresh pick, NOT an advance.
    if pos <= 0 or pos >= len(pl):
        return False
    this_ptr = build_url(action="play", imdb=imdb, mtype="series",
                         season=season_number, episode=episode_number)
    try:
        return pl[pos].getPath() == this_ptr
    except Exception:  # noqa: BLE001
        return False


def _stop_current_if_switching(imdb, mtype, season_number, episode_number) -> None:
    """On a fresh pick, stop the currently-playing item immediately — otherwise
    Kodi keeps it alive (and un-pauses it) on screen while the newly-picked stream
    buffers. Skipped for a next-episode playlist advance, which must flow through."""
    player = xbmc.Player()
    if not player.isPlaying():
        return
    if _is_playlist_advance(imdb, mtype, season_number, episode_number):
        return
    try:
        player.stop()
    except Exception:  # noqa: BLE001 - best-effort
        pass


def play(imdb="", mtype="movie", season_number=0, episode_number=0, url=None,
         title="", quality="", size="", seeders="") -> None:
    # Switching from another movie? Stop it now so it doesn't play on while the
    # new pick buffers (guarded so next-episode autoplay isn't interrupted).
    _stop_current_if_switching(imdb, mtype, season_number, episode_number)
    progress = db.get_progress(imdb, season_number, episode_number) if imdb else None

    # Cinemeta identity (best-effort, never blocks playback): feeds both the info
    # panel AND the expected title, so auto-pick ranks the correct show first.
    meta = {}
    if imdb:
        try:
            meta = cinemeta.meta(mtype, imdb)
        except Exception:  # noqa: BLE001 - info is best-effort
            meta = {}
    expected = meta.get("name", "")

    candidates = []
    if not url:  # one-click Play / Continue Watching
        # Always resolve a FRESH source. TorBox stream links are IP-locked and
        # time-limited, so reusing a stored URL breaks after an IP change or a
        # few hours ("this link has expired / can be watched on this IP only").
        if not config.torbox_token():
            notify("Link your TorBox account first")
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
            return
        ranked = _resolve_ranked(imdb, mtype, season_number, episode_number, expected)
        if not ranked:
            notify("No cached sources found")
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
            return
        best = ranked[0]
        url = best.url
        candidates = [s.url for s in ranked[:FALLBACK_SOURCES]]  # top + fallbacks
        # Carry the auto-picked release's details into the info panel.
        title = title or best.title
        quality = quality or best.quality
        size = size or best.size
        seeders = seeders or (str(best.seeders) if best.seeders else "")

    item = _played_base_item(meta, mtype, season_number, episode_number, url)
    if not meta and title:  # no Cinemeta identity — at least name the release
        item.getVideoInfoTag().setTitle(title)
    _apply_source_info(item, mtype, title, quality, size, seeders)

    if progress and progress.get("duration"):
        ratio = progress["position"] / progress["duration"]
        if 0.01 < ratio < 0.95:
            duration = float(progress["duration"])
            resume_at = max(0.0, float(progress["position"]) - RESUME_REWIND)
            try:
                item.getVideoInfoTag().setResumePoint(resume_at, duration)
            except Exception:  # noqa: BLE001 - fall back to properties below
                pass
            item.setProperty("ResumeTime", str(resume_at))
            item.setProperty("TotalTime", str(duration))

    if imdb:  # tell the service what's playing so it can persist progress + source url
        state = {
            "imdb": imdb, "mtype": mtype,
            "season": season_number or 0, "episode": episode_number or 0,
            "url": url,
        }
        if candidates:  # let the service auto-retry the next source if this fails
            state["candidates"] = candidates
            state["cand_idx"] = 0
        xbmcgui.Window(10000).setProperty(PLAYING_PROP, json.dumps(state))
    xbmcplugin.setResolvedUrl(HANDLE, True, item)

    # Series only: hand Kodi a next-episode to move to, so ⏭ / autoplay-next work.
    # Done after setResolvedUrl so it never delays the current episode starting.
    if mtype == "series" and imdb:
        _queue_next_episode(imdb, season_number, episode_number)


# --- TorBox cloud library --------------------------------------------------
def torbox_list() -> None:
    """Browse the user's own TorBox files — a fallback when indexers come up empty."""
    if not config.torbox_token():
        notify("Link your TorBox account first")
        finish()
        return
    shown = 0
    for t in torbox.mylist():
        fs = torbox.files(t)
        if not fs:
            continue
        name = t.get("name") or fs[0].get("name") or "TorBox item"
        if len(fs) == 1:
            item = xbmcgui.ListItem(label=name)
            item.setProperty("IsPlayable", "true")
            item.getVideoInfoTag().setMediaType("video")
            add_item(item, False, action="torbox_play",
                     torrent_id=t.get("id"), file_id=fs[0].get("id"))
        else:
            add_directory(f"{name}  ({len(fs)})", "torbox_files", torrent_id=t.get("id"))
        shown += 1
    if not shown:
        add_item(xbmcgui.ListItem(label="Your TorBox library is empty"),
                 False, action="noop")
    finish("videos")


def torbox_files(torrent_id) -> None:
    torrent = torbox.get_torrent(torrent_id)
    if not torrent:
        notify("TorBox item not found")
        finish()
        return
    for f in torbox.files(torrent):
        item = xbmcgui.ListItem(label=f.get("short_name") or f.get("name") or "file")
        item.setProperty("IsPlayable", "true")
        item.getVideoInfoTag().setMediaType("video")
        add_item(item, False, action="torbox_play", torrent_id=torrent_id, file_id=f.get("id"))
    finish("videos")


def torbox_play(torrent_id, file_id) -> None:
    if not config.torbox_token():
        notify("Link your TorBox account first")
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return
    url = torbox.request_link(torrent_id, file_id)
    if not url:
        notify("Could not get a link from TorBox")
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return
    # TorBox cloud files aren't IMDb-keyed. Clear the resume-tracking property
    # (set by play()) so the background service doesn't save this file's position
    # against the last movie's identity.
    xbmcgui.Window(10000).clearProperty(PLAYING_PROP)
    xbmcplugin.setResolvedUrl(HANDLE, True, xbmcgui.ListItem(path=url))


def placeholder(title: str) -> None:
    item = xbmcgui.ListItem(label=f"{title} — coming soon")
    add_item(item, False, action="noop")
    finish()


# --- dispatch --------------------------------------------------------------
def router(query_string: str) -> None:
    params = dict(parse_qsl(query_string))
    action = params.get("action")

    if not action:
        home()
    elif action == "menu":
        menu(params["mtype"])
    elif action == "search_menu":
        search_menu()
    elif action == "catalog":
        catalog(params["mtype"], params["cat"])
    elif action == "search":
        search(params["mtype"])
    elif action == "detail":
        detail(params["imdb"], params["mtype"])
    elif action == "season":
        season(params["imdb"], int(params["season"]))
    elif action == "episode":
        episode(params["imdb"], int(params["season"]), int(params["episode"]))
    elif action == "sources":
        sources(
            params.get("imdb", ""),
            params.get("mtype", "movie"),
            int(params["season"]) if params.get("season") else None,
            int(params["episode"]) if params.get("episode") else None,
        )
    elif action == "play":
        play(
            params.get("imdb", ""),
            params.get("mtype", "movie"),
            int(params["season"]) if params.get("season") else 0,
            int(params["episode"]) if params.get("episode") else 0,
            params.get("url"),
            params.get("title", ""),
            params.get("quality", ""),
            params.get("size", ""),
            params.get("seeders", ""),
        )
    elif action == "auth_torbox":
        auth.run_device_auth()
        xbmc.executebuiltin("Container.Refresh")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    elif action == "continue":
        continue_watching()
    elif action == "cw_menu":
        cw_menu(
            params.get("imdb", ""),
            params.get("mtype", "movie"),
            int(params["season"]) if params.get("season") else 0,
            int(params["episode"]) if params.get("episode") else 0,
        )
    elif action == "torbox_list":
        torbox_list()
    elif action == "torbox_files":
        torbox_files(params.get("torrent_id", ""))
    elif action == "torbox_play":
        torbox_play(params.get("torrent_id", ""), params.get("file_id", ""))
    elif action == "watchlist":
        watchlist()
    elif action == "wl_folder":
        wl_folder(int(params["folder"]))
    elif action == "wl_add":
        wl_add(params.get("imdb", ""), params.get("mtype", "movie"),
               params.get("name", ""), params.get("poster", ""))
    elif action == "wl_move":
        wl_move(params.get("imdb", ""))
    elif action == "wl_newfolder":
        wl_newfolder()
    elif action == "wl_renamefolder":
        wl_renamefolder(int(params["folder"]))
    elif action == "wl_delfolder":
        wl_delfolder(int(params["folder"]))
    elif action == "wl_remove":
        wl_remove(params.get("imdb", ""))
    elif action in ("wl_options", "wl_reorder", "wl_grab", "wl_grabcancel", "wl_drop",
                    "wl_reorder_done", "wl_pinmode", "wl_pintoggle", "wl_pinmode_done"):
        folder_id = int(params["folder"]) if params.get("folder") else None
        if action == "wl_options":
            wl_options(folder_id)
        elif action == "wl_reorder":
            wl_reorder(folder_id)
        elif action == "wl_grab":
            wl_grab(params.get("key", ""), folder_id)
        elif action == "wl_grabcancel":
            wl_grabcancel(folder_id)
        elif action == "wl_drop":
            wl_drop(params.get("before", "__bottom__"), folder_id)
        elif action == "wl_reorder_done":
            wl_reorder_done(folder_id)
        elif action == "wl_pinmode":
            wl_pinmode(folder_id)
        elif action == "wl_pintoggle":
            wl_pintoggle(params.get("key", ""), folder_id)
        elif action == "wl_pinmode_done":
            wl_pinmode_done(folder_id)
    elif action == "noop":
        finish()
    else:
        home()


if __name__ == "__main__":
    try:
        router(sys.argv[2][1:])
    except HttpError as exc:
        log(f"network error: {exc}")
        notify("Network/API error — check your connection")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    except Exception as exc:  # noqa: BLE001 - last-resort guard so Kodi never hangs
        log(f"unhandled error: {exc}")
        notify(f"Error: {exc}")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
