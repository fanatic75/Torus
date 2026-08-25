"""Build Kodi ListItems from TMDB dicts.

Uses the Kodi 21 (Omega) InfoTagVideo setters (getVideoInfoTag()), not the
deprecated setInfo() dict. Rich art + metadata here is what lets a good skin
render the Stremio-like poster rows without us drawing any custom UI.
"""
import xbmcgui

from .. import tmdb


def _year(date_str: str | None) -> int | None:
    if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
        return int(date_str[:4])
    return None


def movie_item(movie: dict) -> xbmcgui.ListItem:
    item = xbmcgui.ListItem(label=movie.get("title", ""))
    tag = item.getVideoInfoTag()
    tag.setMediaType("movie")
    tag.setTitle(movie.get("title", ""))
    tag.setPlot(movie.get("overview", ""))
    year = _year(movie.get("release_date"))
    if year:
        tag.setYear(year)
    if movie.get("vote_average"):
        tag.setRating(float(movie["vote_average"]))
    ids = {"tmdb": str(movie["id"])}
    imdb = movie.get("external_ids", {}).get("imdb_id")
    if imdb:
        ids["imdb"] = imdb
    tag.setUniqueIDs(ids, "tmdb")
    poster = tmdb.poster(movie.get("poster_path"))
    item.setArt({
        "poster": poster,
        "thumb": poster,
        "fanart": tmdb.backdrop(movie.get("backdrop_path")),
    })
    return item


def tvshow_item(show: dict) -> xbmcgui.ListItem:
    item = xbmcgui.ListItem(label=show.get("name", ""))
    tag = item.getVideoInfoTag()
    tag.setMediaType("tvshow")
    tag.setTitle(show.get("name", ""))
    tag.setPlot(show.get("overview", ""))
    year = _year(show.get("first_air_date"))
    if year:
        tag.setYear(year)
    if show.get("vote_average"):
        tag.setRating(float(show["vote_average"]))
    ids = {"tmdb": str(show["id"])}
    imdb = show.get("external_ids", {}).get("imdb_id")
    if imdb:
        ids["imdb"] = imdb
    tag.setUniqueIDs(ids, "tmdb")
    poster = tmdb.poster(show.get("poster_path"))
    item.setArt({
        "poster": poster,
        "thumb": poster,
        "fanart": tmdb.backdrop(show.get("backdrop_path")),
    })
    return item


def season_item(show: dict, season: dict) -> xbmcgui.ListItem:
    label = season.get("name") or f"Season {season.get('season_number')}"
    item = xbmcgui.ListItem(label=label)
    tag = item.getVideoInfoTag()
    tag.setMediaType("season")
    tag.setTitle(label)
    tag.setTvShowTitle(show.get("name", ""))
    tag.setPlot(season.get("overview", ""))
    if season.get("season_number") is not None:
        tag.setSeason(int(season["season_number"]))
    poster = tmdb.poster(season.get("poster_path") or show.get("poster_path"))
    item.setArt({"poster": poster, "thumb": poster,
                 "fanart": tmdb.backdrop(show.get("backdrop_path"))})
    return item


def episode_item(show: dict, episode: dict) -> xbmcgui.ListItem:
    number = episode.get("episode_number")
    label = f"{number}. {episode.get('name', '')}".strip(". ")
    item = xbmcgui.ListItem(label=label)
    tag = item.getVideoInfoTag()
    tag.setMediaType("episode")
    tag.setTitle(episode.get("name", ""))
    tag.setTvShowTitle(show.get("name", ""))
    tag.setPlot(episode.get("overview", ""))
    if episode.get("season_number") is not None:
        tag.setSeason(int(episode["season_number"]))
    if number is not None:
        tag.setEpisode(int(number))
    if episode.get("vote_average"):
        tag.setRating(float(episode["vote_average"]))
    still = tmdb.backdrop(episode.get("still_path"), size="w780")
    item.setArt({
        "thumb": still,
        "fanart": tmdb.backdrop(show.get("backdrop_path")),
        "poster": tmdb.poster(show.get("poster_path")),
    })
    return item
