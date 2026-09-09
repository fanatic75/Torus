"""Provider parsing, merge/dedup, and the factory."""
import threading
import time

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


class _Hang(Provider):
    """A provider that blocks (simulates elfhosted/Comet stalling for its full
    timeout). `released` lets the test unblock the background thread so nothing
    lingers after the assertions."""
    def __init__(self):
        self.released = threading.Event()

    def search(self, *a, **k):
        self.released.wait(timeout=30)
        return [Stream("SLOW 2160p", "slow")]


def test_merged_does_not_block_on_a_hanging_provider():
    # REGRESSION: with provider="both", a dead/stalled provider must NOT hold up
    # the working one — previously the merge waited for the slowest (~15-60s),
    # so Play / Choose source appeared to do nothing. Now the fast provider's
    # results come back immediately and the hung one is left behind.
    fast = _Fake([Stream("FAST 1080p", "fast")])
    hang = _Hang()
    merged = MergedProvider([fast, hang], straggler_grace=0.3, search_timeout=5)

    start = time.time()
    streams = merged.search("tt1", "movie")
    elapsed = time.time() - start
    hang.released.set()  # let the background thread finish; nothing left hanging

    assert [s.url for s in streams] == ["fast"]              # working provider's results
    assert elapsed < 2, f"merge blocked {elapsed:.1f}s on the hung provider"


def test_merged_still_waits_within_grace_for_a_slightly_slower_provider():
    # A merely-slower (not dead) provider still gets merged, as long as it answers
    # within the grace window — so we don't lose coverage when both are healthy.
    class _SlowButAlive(Provider):
        def search(self, *a, **k):
            time.sleep(0.15)
            return [Stream("B 2160p", "ub")]

    merged = MergedProvider([_Fake([Stream("A 1080p", "ua")]), _SlowButAlive()],
                            straggler_grace=1.0, search_timeout=5)
    urls = {s.url for s in merged.search("tt1", "movie")}
    assert urls == {"ua", "ub"}


# --- factory ---------------------------------------------------------------
def test_get_provider_by_setting(monkeypatch):
    monkeypatch.setattr(config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(config, "provider", lambda: "comet")
    assert isinstance(get_provider(), comet.CometProvider)
    monkeypatch.setattr(config, "provider", lambda: "torrentio")
    assert isinstance(get_provider(), torrentio.TorrentioProvider)
    monkeypatch.setattr(config, "provider", lambda: "both")
    assert isinstance(get_provider(), MergedProvider)


# --- infohash extraction + infohash-based dedup ---------------------------
def test_comet_infohash_from_bingegroup():
    assert comet._infohash({"behaviorHints": {"bingeGroup": "comet|torbox|" + "a" * 40}}) == "a" * 40
    assert comet._infohash({"behaviorHints": {}}) == ""
    assert comet._infohash({}) == ""


def test_torrentio_infohash_from_url(monkeypatch):
    ih = "b" * 40
    payload = {"streams": [
        {"url": "https://torrentio.strem.fun/resolve/torbox/KEY/%s/6/File.mkv" % ih,
         "name": "Torrentio\n[TB+]", "title": "Movie 1080p",
         "behaviorHints": {"filename": "File.mkv"}},
    ]}
    monkeypatch.setattr(torrentio, "get_json", lambda *a, **k: payload)
    assert torrentio.TorrentioProvider("KEY").search("tt1", "movie")[0].infohash == ih


def test_merged_dedups_by_infohash_prefers_first_provider():
    ih = "c" * 40
    tor = _Fake([Stream("Dark.S02E07.2160p-NTb", "torrentio-url", infohash=ih)])
    com = _Fake([Stream("Totally Different Parsed Name", "comet-url", infohash=ih)])
    # same torrent, different titles/urls -> deduped by infohash; first (Torrentio) kept
    merged = MergedProvider([tor, com]).search("tt1", "series")
    assert [s.url for s in merged] == ["torrentio-url"]


def test_merged_keeps_different_infohashes():
    tor = _Fake([Stream("A", "ua", infohash="a" * 40)])
    com = _Fake([Stream("B", "ub", infohash="d" * 40)])
    assert {s.url for s in MergedProvider([tor, com]).search("tt1", "series")} == {"ua", "ub"}
