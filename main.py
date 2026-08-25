"""Torus plugin entry point (router).

Kodi invokes this file for every navigation action with three argv values:
    argv[0] -> base plugin url, e.g. "plugin://plugin.video.torus/"
    argv[1] -> the integer handle Kodi expects us to fill with a directory
    argv[2] -> the query string, e.g. "?action=catalog&kind=movie&list=trending"

The model is stateless request/response: parse the action, build a listing,
call endOfDirectory, exit. `router()` is the HTTP-router analogue.

M1 scope: TMDB discovery. Playable leaves are placeholders until M3.
"""
import sys
from urllib.parse import urlencode, parse_qsl

import xbmc
import xbmcgui
import xbmcplugin

from resources.lib import auth, config, providers, ranking, tmdb
from resources.lib.http import HttpError, log
from resources.lib.kodi import listing

HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]


# --- url + item helpers ----------------------------------------------------
def build_url(**kwargs) -> str:
    return f"{BASE_URL}?{urlencode(kwargs)}"


def add_directory(label: str, action: str, art: dict | None = None, **extra) -> None:
    item = xbmcgui.ListItem(label=label)
    item.setArt(art or {"icon": "DefaultFolder.png"})
    xbmcplugin.addDirectoryItem(HANDLE, build_url(action=action, **extra), item, isFolder=True)


def add_item(item: xbmcgui.ListItem, is_folder: bool, **params) -> None:
    xbmcplugin.addDirectoryItem(HANDLE, build_url(**params), item, isFolder=is_folder)


def finish(content: str | None = None) -> None:
    if content:
        xbmcplugin.setContent(HANDLE, content)
    xbmcplugin.endOfDirectory(HANDLE)


def notify(message: str) -> None:
    xbmcgui.Dialog().notification("Torus", message, xbmcgui.NOTIFICATION_WARNING)


# --- views -----------------------------------------------------------------
def home() -> None:
    # First-run onboarding: link TorBox with the device-code flow (no typing).
    if not config.torbox_token():
        link = xbmcgui.ListItem(label="🔗  Link your TorBox account")
        link.setArt({"icon": "DefaultAddonService.png"})
        xbmcplugin.addDirectoryItem(
            HANDLE, build_url(action="auth_torbox"), link, isFolder=False
        )
    add_directory("Movies", "movies")
    add_directory("TV Shows", "tv")
    add_directory("Search", "search_menu")
    add_directory("Continue Watching", "continue")
    finish()


def movies_menu() -> None:
    add_directory("Trending", "catalog", kind="movie", list="trending")
    add_directory("Popular", "catalog", kind="movie", list="popular")
    add_directory("Search Movies", "search", kind="movie")
    finish()


def tv_menu() -> None:
    add_directory("Trending", "catalog", kind="tv", list="trending")
    add_directory("Popular", "catalog", kind="tv", list="popular")
    add_directory("Search TV", "search", kind="tv")
    finish()


def search_menu() -> None:
    add_directory("Search Movies", "search", kind="movie")
    add_directory("Search TV", "search", kind="tv")
    finish()


_CATALOG = {
    ("movie", "trending"): tmdb.trending_movies,
    ("movie", "popular"): tmdb.popular_movies,
    ("tv", "trending"): tmdb.trending_tv,
    ("tv", "popular"): tmdb.popular_tv,
}


def catalog(kind: str, list_name: str) -> None:
    results = _CATALOG[(kind, list_name)]()
    _render_results(kind, results)


def search(kind: str) -> None:
    query = xbmcgui.Dialog().input("Search", type=xbmcgui.INPUT_ALPHANUM)
    if not query:
        finish()
        return
    results = tmdb.search_movies(query) if kind == "movie" else tmdb.search_tv(query)
    _render_results(kind, results)


def _render_results(kind: str, results: list) -> None:
    if kind == "movie":
        for movie in results:
            add_item(listing.movie_item(movie), True,
                     action="movie_detail", tmdb_id=movie["id"])
        finish("movies")
    else:
        for show in results:
            add_item(listing.tvshow_item(show), True,
                     action="tv_detail", tmdb_id=show["id"])
        finish("tvshows")


def movie_detail(tmdb_id: int) -> None:
    detail = tmdb.movie_detail(tmdb_id)
    imdb = detail.get("external_ids", {}).get("imdb_id", "")
    # Find playable TorBox-cached sources for this movie.
    find = listing.movie_item(detail)
    find.setLabel(f"▶  Find sources — {detail.get('title', '')}")
    add_item(find, True, action="sources", imdb=imdb, mtype="movie")
    # Similar titles, browsable.
    for movie in detail.get("similar", {}).get("results", []):
        add_item(listing.movie_item(movie), True,
                 action="movie_detail", tmdb_id=movie["id"])
    finish("movies")


def tv_detail(tmdb_id: int) -> None:
    detail = tmdb.tv_detail(tmdb_id)
    for season in detail.get("seasons", []):
        item = listing.season_item(detail, season)
        add_item(item, True, action="season",
                 tmdb_id=tmdb_id, season=season.get("season_number", 0))
    finish("seasons")


def season(tmdb_id: int, season_number: int) -> None:
    show = tmdb.tv_detail(tmdb_id)
    imdb = show.get("external_ids", {}).get("imdb_id", "")
    data = tmdb.tv_season(tmdb_id, season_number)
    for episode in data.get("episodes", []):
        item = listing.episode_item(show, episode)
        add_item(item, True, action="sources", imdb=imdb, mtype="series",
                 season=season_number, episode=episode.get("episode_number", 0))
    finish("episodes")


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
    streams = ranking.rank(
        provider.search(imdb, mtype, season_number, episode_number)
    )
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
        if not config.tmdb_key():
            notify("Set your TMDB API key in Torus settings")
        home()
    elif action == "movies":
        movies_menu()
    elif action == "tv":
        tv_menu()
    elif action == "search_menu":
        search_menu()
    elif action == "catalog":
        catalog(params["kind"], params["list"])
    elif action == "search":
        search(params["kind"])
    elif action == "movie_detail":
        movie_detail(int(params["tmdb_id"]))
    elif action == "tv_detail":
        tv_detail(int(params["tmdb_id"]))
    elif action == "season":
        season(int(params["tmdb_id"]), int(params["season"]))
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
        notify("Network/API error — check your TMDB key")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    except Exception as exc:  # noqa: BLE001 - last-resort guard so Kodi never hangs
        log(f"unhandled error: {exc}")
        notify(f"Error: {exc}")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
