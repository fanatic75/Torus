"""Torus plugin entry point (router).

Kodi invokes this file for every navigation action with three argv values:
    argv[0] -> base plugin url, e.g. "plugin://plugin.video.torus/"
    argv[1] -> the integer handle Kodi expects us to fill with a directory
    argv[2] -> the query string, e.g. "?action=catalog&mtype=movie&cat=top"

Stateless request/response: parse the action, build a listing, endOfDirectory,
exit. Metadata is Cinemeta (keyless, IMDb-keyed); sources come from the provider
layer (Comet) and play via setResolvedUrl.
"""

from __future__ import annotations
import json
import sys
from urllib.parse import urlencode, parse_qsl

import xbmc
import xbmcgui
import xbmcplugin

from resources.lib import auth, cinemeta, config, db, providers, ranking, release_groups
from resources.lib.http import HttpError, log
from resources.lib.kodi import listing

PLAYING_PROP = "torus.playing"
# Rewind a few seconds on resume so it's easy to pick up where you left off.
RESUME_REWIND = 10

HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]


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
    if not config.torbox_token():
        link = xbmcgui.ListItem(label="🔗  Link your TorBox account")
        link.setArt({"icon": "DefaultAddonService.png"})
        xbmcplugin.addDirectoryItem(HANDLE, build_url(action="auth_torbox"), link, isFolder=False)
    add_directory("Movies", "menu", mtype="movie")
    add_directory("TV Shows", "menu", mtype="series")
    add_directory("Search", "search_menu")
    add_directory("Continue Watching", "continue")
    add_directory("My List", "watchlist")
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
    """Context-menu entry to add/remove a title from My List."""
    if in_list:
        return [("Remove from My List",
                 f"RunPlugin({build_url(action='wl_remove', imdb=imdb)})")]
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
        item.setProperty("IsPlayable", "true")
        tag = item.getVideoInfoTag()
        tag.setMediaType("movie" if row.get("mtype") == "movie" else "episode")
        tag.setTitle(row.get("name") or "")
        item.addContextMenuItems(_choose_source_ctx(
            row["imdb"], row.get("mtype", "movie"), row.get("season", 0), row.get("episode", 0)))
        add_item(item, False, action="play", imdb=row["imdb"], mtype=row.get("mtype", "movie"),
                 season=row.get("season", 0), episode=row.get("episode", 0))
    finish()


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

    provider = providers.get_provider()
    streams = ranking.rank(provider.search(imdb, mtype, season_number, episode_number))
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
                 season=season_number or 0, episode=episode_number or 0)
    finish()


def _resolve_best(imdb, mtype, season_number, episode_number) -> str | None:
    provider = providers.get_provider()
    streams = ranking.rank(provider.search(imdb, mtype,
                                            season_number or None, episode_number or None))
    return streams[0].url if streams else None


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


def watchlist() -> None:
    rows = db.list_watchlist()
    if not rows:
        item = xbmcgui.ListItem(label="Your list is empty — add titles from any movie or show")
        add_item(item, False, action="noop")
        finish()
        return
    for row in rows:
        meta_like = {"id": row["imdb"], "name": row["name"],
                     "type": row["mtype"], "poster": row["poster"]}
        item = listing.catalog_item(meta_like)
        item.addContextMenuItems(
            _watchlist_ctx(row["imdb"], row["mtype"], row["name"], row["poster"], True))
        add_item(item, True, action="detail", imdb=row["imdb"], mtype=row["mtype"])
    finish("movies")


def _after_watchlist_change() -> None:
    if HANDLE >= 0:  # a clicked toggle item; RunPlugin context-menu passes handle -1
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    xbmc.executebuiltin("Container.Refresh")


def wl_add(imdb, mtype="movie", name="", poster="") -> None:
    db.add_watchlist(imdb, mtype, name, poster)
    xbmcgui.Dialog().notification("Torus", "Added to My List", xbmcgui.NOTIFICATION_INFO)
    _after_watchlist_change()


def wl_remove(imdb) -> None:
    db.remove_watchlist(imdb)
    xbmcgui.Dialog().notification("Torus", "Removed from My List", xbmcgui.NOTIFICATION_INFO)
    _after_watchlist_change()


def play(imdb="", mtype="movie", season_number=0, episode_number=0, url=None) -> None:
    progress = db.get_progress(imdb, season_number, episode_number) if imdb else None

    if not url:  # one-click Play / Continue Watching
        # Always resolve a FRESH source. TorBox stream links are IP-locked and
        # time-limited, so reusing a stored URL breaks after an IP change or a
        # few hours ("this link has expired / can be watched on this IP only").
        if not config.torbox_token():
            notify("Link your TorBox account first")
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
            return
        url = _resolve_best(imdb, mtype, season_number, episode_number)
        if not url:
            notify("No cached sources found")
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
            return

    item = xbmcgui.ListItem(path=url)
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
        xbmcgui.Window(10000).setProperty(PLAYING_PROP, json.dumps({
            "imdb": imdb, "mtype": mtype,
            "season": season_number or 0, "episode": episode_number or 0,
            "url": url,
        }))
    xbmcplugin.setResolvedUrl(HANDLE, True, item)

    # Series only: hand Kodi a next-episode to move to, so ⏭ / autoplay-next work.
    # Done after setResolvedUrl so it never delays the current episode starting.
    if mtype == "series" and imdb:
        _queue_next_episode(imdb, season_number, episode_number)


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
        )
    elif action == "auth_torbox":
        auth.run_device_auth()
        xbmc.executebuiltin("Container.Refresh")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    elif action == "continue":
        continue_watching()
    elif action == "watchlist":
        watchlist()
    elif action == "wl_add":
        wl_add(params.get("imdb", ""), params.get("mtype", "movie"),
               params.get("name", ""), params.get("poster", ""))
    elif action == "wl_remove":
        wl_remove(params.get("imdb", ""))
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
