"""Provider parsing, merge/dedup, and the factory."""
from resources.lib.providers import comet, torrentio, MergedProvider, get_provider
from resources.lib.providers.base import Provider, Stream
from resources.lib import config


# --- Comet parsing ---------------------------------------------------------
def test_comet_helpers():
    desc = "📄 Movie.2024.2160p.REMUX-FraMeSToR\n💾 60 GB 👤 42"
    assert comet._release_title(desc) == "Movie.2024.2160p.REMUX-FraMeSToR"
    assert comet._size(desc) == "60 GB"
    assert comet._seeders(desc) == 42
    assert comet._quality("something 2160p uhd") == "2160p"


def test_comet_search_parses_and_skips_urlless(monkeypatch):
    payload = {"streams": [
        {"url": "http://x/1", "name": "Torrentio\n2160p ⚡",
         "description": "📄 Movie.2024.2160p.REMUX-FraMeSToR\n💾 60 GB 👤 42"},
        {"name": "sync your account", "description": "no url here"},  # must be skipped
    ]}
    monkeypatch.setattr(comet, "get_json", lambda *a, **k: payload)
    streams = comet.CometProvider("KEY").search("tt1", "movie")
    assert len(streams) == 1
    st = streams[0]
    assert "FraMeSToR" in st.title
    assert st.quality == "2160p"
    assert st.size == "60 GB"
    assert st.seeders == 42
    assert st.cached is True


# --- Torrentio parsing -----------------------------------------------------
def test_torrentio_search_filters_uncached(monkeypatch):
    payload = {"streams": [
        {"url": "u1", "name": "Torrentio\n[TB+] ⚡",
         "title": "Movie.2024.1080p.WEB-DL-FLUX\n👤 10 💾 8 GB",
         "behaviorHints": {"filename": "Movie.2024.1080p.WEB-DL-FLUX.mkv"}},
        {"url": "u2", "name": "Torrentio 1080p"},  # no [TB+]/⚡ -> uncached, skipped
    ]}
    monkeypatch.setattr(torrentio, "get_json", lambda *a, **k: payload)
    streams = torrentio.TorrentioProvider("KEY").search("tt1", "movie")
    assert len(streams) == 1
    assert streams[0].title == "Movie.2024.1080p.WEB-DL-FLUX.mkv"
    assert streams[0].quality == "1080p"
    assert streams[0].seeders == 10


def test_comet_stream_id_series():
    p = comet.CometProvider("K")
    assert p._stream_id("tt1", "series", 2, 5) == "tt1:2:5"
    assert p._stream_id("tt1", "movie", None, None) == "tt1"


# --- Merge + dedup ---------------------------------------------------------
class _Fake(Provider):
    def __init__(self, streams): self._s = streams
    def search(self, *a, **k): return self._s


class _Boom(Provider):
    def search(self, *a, **k): raise RuntimeError("provider down")


def test_merged_dedups_by_normalized_title():
    a = _Fake([Stream("Movie 2160p REMUX", "ua")])
    b = _Fake([Stream("Movie.2160p.REMUX", "ub"), Stream("Other 1080p", "uc")])
    merged = MergedProvider([a, b]).search("tt1", "movie")
    titles = [s.title for s in merged]
    assert titles == ["Movie 2160p REMUX", "Other 1080p"]  # dup dropped, order stable


def test_merged_tolerates_a_failing_provider():
    merged = MergedProvider([_Boom(), _Fake([Stream("X 1080p", "u")])]).search("tt1", "movie")
    assert [s.title for s in merged] == ["X 1080p"]


# --- factory ---------------------------------------------------------------
def test_get_provider_by_setting(monkeypatch):
    monkeypatch.setattr(config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(config, "provider", lambda: "comet")
    assert isinstance(get_provider(), comet.CometProvider)
    monkeypatch.setattr(config, "provider", lambda: "torrentio")
    assert isinstance(get_provider(), torrentio.TorrentioProvider)
    monkeypatch.setattr(config, "provider", lambda: "both")
    assert isinstance(get_provider(), MergedProvider)
