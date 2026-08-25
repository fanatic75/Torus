"""TMDB client — discovery, search, detail, and image URLs.

Everything the user browses comes from here. The TMDB id is our common handle;
`external_ids` gives the IMDb id that providers (Comet/Torrentio) need later.
"""
import urllib.parse

from . import config
from .http import get_json

BASE = "https://api.themoviedb.org/3"
IMAGE = "https://image.tmdb.org/t/p"


def _get(path: str, extra: dict | None = None) -> dict:
    params = {"api_key": config.tmdb_key()}
    if extra:
        params.update(extra)
    return get_json(f"{BASE}{path}", params)


# --- catalogs --------------------------------------------------------------
def trending_movies() -> list[dict]:
    return _get("/trending/movie/week").get("results", [])


def popular_movies() -> list[dict]:
    return _get("/movie/popular").get("results", [])


def trending_tv() -> list[dict]:
    return _get("/trending/tv/week").get("results", [])


def popular_tv() -> list[dict]:
    return _get("/tv/popular").get("results", [])


def search_movies(query: str) -> list[dict]:
    return _get("/search/movie", {"query": query}).get("results", [])


def search_tv(query: str) -> list[dict]:
    return _get("/search/tv", {"query": query}).get("results", [])


# --- detail ----------------------------------------------------------------
def movie_detail(tmdb_id: int) -> dict:
    return _get(f"/movie/{tmdb_id}",
                {"append_to_response": "external_ids,credits,similar"})


def tv_detail(tmdb_id: int) -> dict:
    return _get(f"/tv/{tmdb_id}",
                {"append_to_response": "external_ids,credits,similar"})


def tv_season(tmdb_id: int, season_number: int) -> dict:
    return _get(f"/tv/{tmdb_id}/season/{season_number}")


# --- images ----------------------------------------------------------------
def _maybe_proxy(url: str) -> str:
    """Kodi's image loader uses the SYSTEM DNS, which our in-addon DoH can't fix.
    So when the proxy is enabled, rewrite TMDB image URLs through a proxy host
    that the ISP doesn't block, keeping posters working behind DNS blocks."""
    if not url or not config.image_proxy():
        return url
    without_scheme = url.split("://", 1)[-1]
    return "https://images.weserv.nl/?url=" + urllib.parse.quote(without_scheme, safe="")


def poster(path: str | None, size: str = "w500") -> str:
    return _maybe_proxy(f"{IMAGE}/{size}{path}") if path else ""


def backdrop(path: str | None, size: str = "w1280") -> str:
    return _maybe_proxy(f"{IMAGE}/{size}{path}") if path else ""
