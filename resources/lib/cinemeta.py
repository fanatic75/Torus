"""Cinemeta metadata client — Stremio's public, keyless metadata API.

No API key, no signup, and it's IMDb-keyed — which is exactly what our source
providers (Comet) consume, so there's no id bridging. This is the same metadata
backend Stremio itself uses.

Catalogs (per type movie|series): top (Popular), imdbRating (Top Rated),
year (New). Each supports genre / search / skip.
"""

from __future__ import annotations
import urllib.parse

from . import config
from .http import get_json

BASE = "https://v3-cinemeta.strem.io"


def catalog(media_type: str, cat_id: str, search: str | None = None,
            genre: str | None = None, skip: int = 0) -> list[dict]:
    path = f"/catalog/{media_type}/{cat_id}"
    extras = []
    if search:
        extras.append(f"search={urllib.parse.quote(search)}")
    if genre:
        extras.append(f"genre={urllib.parse.quote(genre)}")
    if skip:
        extras.append(f"skip={skip}")
    if extras:
        path += "/" + "&".join(extras)
    return get_json(f"{BASE}{path}.json").get("metas", [])


def meta(media_type: str, imdb_id: str) -> dict:
    return get_json(f"{BASE}/meta/{media_type}/{imdb_id}.json").get("meta", {})


def image(url: str | None) -> str:
    """Optionally route images through a proxy so ISP-blocked image hosts still
    load in Kodi's image loader (which uses system DNS, not our DoH)."""
    if not url:
        return ""
    if not config.image_proxy():
        return url
    return "https://images.weserv.nl/?url=" + urllib.parse.quote(
        url.split("://", 1)[-1], safe=""
    )
