"""Build Kodi ListItems from Cinemeta metadata dicts.

Uses the Kodi 21 (Omega) InfoTagVideo setters. Rich art + metadata here is what
lets a good skin render Stremio-like poster rows without custom UI code.
"""

from __future__ import annotations
import xbmcgui

from .. import cinemeta


def _year(release_info) -> int | None:
    text = str(release_info or "")[:4]
    return int(text) if text.isdigit() else None


def _apply_common(item: xbmcgui.ListItem, meta: dict):
    tag = item.getVideoInfoTag()
    tag.setTitle(meta.get("name", ""))
    tag.setPlot(meta.get("description", "") or "")
    year = _year(meta.get("releaseInfo"))
    if year:
        tag.setYear(year)
    rating = meta.get("imdbRating")
    if rating:
        try:
            tag.setRating(float(rating))
        except (TypeError, ValueError):
            pass
    genres = meta.get("genres") or []
    if genres:
        tag.setGenres(genres)
    imdb = meta.get("id") or meta.get("imdb_id") or ""
    if imdb:
        tag.setUniqueIDs({"imdb": imdb}, "imdb")
    return tag


def catalog_item(meta: dict) -> xbmcgui.ListItem:
    item = xbmcgui.ListItem(label=meta.get("name", ""))
    tag = _apply_common(item, meta)
    tag.setMediaType("movie" if meta.get("type") == "movie" else "tvshow")
    poster = cinemeta.image(meta.get("poster"))
    item.setArt({
        "poster": poster,
        "thumb": poster,
        "fanart": cinemeta.image(meta.get("background")),
    })
    return item


def season_item(show: dict, season_number: int) -> xbmcgui.ListItem:
    item = xbmcgui.ListItem(label=f"Season {season_number}")
    tag = item.getVideoInfoTag()
    tag.setMediaType("season")
    tag.setTitle(f"Season {season_number}")
    tag.setTvShowTitle(show.get("name", ""))
    tag.setSeason(int(season_number))
    poster = cinemeta.image(show.get("poster"))
    item.setArt({
        "poster": poster,
        "thumb": poster,
        "fanart": cinemeta.image(show.get("background")),
    })
    return item


def episode_item(show: dict, video: dict) -> xbmcgui.ListItem:
    number = video.get("episode", 0)
    name = video.get("name", "")
    item = xbmcgui.ListItem(label=f"{number}. {name}".strip(". "))
    tag = item.getVideoInfoTag()
    tag.setMediaType("episode")
    tag.setTitle(name)
    tag.setTvShowTitle(show.get("name", ""))
    if video.get("season") is not None:
        tag.setSeason(int(video.get("season", 0)))
    if number:
        tag.setEpisode(int(number))
    tag.setPlot(video.get("overview", "") or "")
    poster = cinemeta.image(show.get("poster"))
    thumb = cinemeta.image(video.get("thumbnail")) or poster
    item.setArt({
        "thumb": thumb,
        "poster": poster,
        "fanart": cinemeta.image(show.get("background")),
    })
    return item
