"""Torus plugin entry point (router).

Kodi invokes this file for every navigation action with three argv values:
    argv[0] -> base plugin url, e.g. "plugin://plugin.video.torus/"
    argv[1] -> the integer handle Kodi expects us to fill with a directory
    argv[2] -> the query string, e.g. "?action=catalog&mtype=movie&cat=top"

Stateless request/response: parse the action, build a listing, endOfDirectory,
exit. Metadata is Cinemeta (keyless, IMDb-keyed); sources come from the provider
layer (Comet) and play via setResolvedUrl.
"""
import sys
from urllib.parse import urlencode, parse_qsl

import xbmc
import xbmcgui
import xbmcplugin

from resources.lib import auth, cinemeta, config, providers, ranking
from resources.lib.http import HttpError, log
from resources.lib.kodi import listing

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
    for meta in metas:
        imdb = meta.get("id") or meta.get("imdb_id")
        if not imdb:
            continue
        add_item(listing.catalog_item(meta), True,
                 action="detail", imdb=imdb, mtype=mtype)
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
def detail(imdb: str, mtype: str) -> None:
    meta = cinemeta.meta(mtype, imdb)
    if mtype == "movie":
        find = listing.catalog_item(meta)
        find.setLabel(f"▶  Find sources — {meta.get('name', '')}")
        add_item(find, True, action="sources", imdb=imdb, mtype="movie")
        finish("movies")
        return
    # series: list seasons derived from the episode videos
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
        add_item(listing.episode_item(meta, video), True,
                 action="sources", imdb=imdb, mtype="series",
                 season=season_number, episode=video.get("episode", 0))
    finish("episodes")


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
        bits = [b for b in (stream.quality, stream.size) if b]
        prefix = f"[{' · '.join(bits)}] " if bits else ""
        item = xbmcgui.ListItem(label=f"{prefix}{stream.title}")
        item.setProperty("IsPlayable", "true")
        tag = item.getVideoInfoTag()
        tag.setMediaType("movie" if mtype == "movie" else "episode")
        tag.setTitle(stream.title)
        add_item(item, False, action="play", url=stream.url)
    finish()


def play(url: str) -> None:
    item = xbmcgui.ListItem(path=url)
    xbmcplugin.setResolvedUrl(HANDLE, True, item)


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
    elif action == "sources":
        sources(
            params.get("imdb", ""),
            params.get("mtype", "movie"),
            int(params["season"]) if params.get("season") else None,
            int(params["episode"]) if params.get("episode") else None,
        )
    elif action == "play":
        play(params["url"])
    elif action == "auth_torbox":
        auth.run_device_auth()
        xbmc.executebuiltin("Container.Refresh")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    elif action == "continue":
        placeholder("Continue Watching")
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
