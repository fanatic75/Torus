"""ListItem builders (exercise the xbmcgui-dependent path via conftest stubs)."""
from resources.lib.kodi import listing
from resources.lib import config


def test_catalog_item_movie(monkeypatch):
    monkeypatch.setattr(config, "image_proxy", lambda: False)  # passthrough images
    meta = {"name": "M", "type": "movie", "description": "plot",
            "releaseInfo": "2024", "imdbRating": "7.5", "genres": ["Action"],
            "id": "tt1", "poster": "http://p", "background": "http://b"}
    item = listing.catalog_item(meta)
    tag = item.getVideoInfoTag()
    assert tag.getTitle() == "M"
    assert tag.getMediaType() == "movie"
    assert tag.getYear() == 2024
    assert item._art["poster"] == "http://p"


def test_catalog_item_series_mediatype(monkeypatch):
    monkeypatch.setattr(config, "image_proxy", lambda: False)
    item = listing.catalog_item({"name": "S", "type": "series", "id": "tt2"})
    assert item.getVideoInfoTag().getMediaType() == "tvshow"


def test_episode_item(monkeypatch):
    monkeypatch.setattr(config, "image_proxy", lambda: False)
    show = {"name": "Show", "poster": "http://p", "background": "http://b"}
    video = {"season": 1, "episode": 2, "name": "Ep Name",
             "overview": "ov", "thumbnail": "http://t"}
    item = listing.episode_item(show, video)
    tag = item.getVideoInfoTag()
    assert tag.getTitle() == "Ep Name"
    assert tag.getMediaType() == "episode"
    assert tag.getSeason() == 1
    assert tag.getEpisode() == 2
    assert item._art["thumb"] == "http://t"
