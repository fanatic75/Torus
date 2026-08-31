"""TorBox cloud-library API module."""
from resources.lib import torbox


def test_is_video():
    assert torbox.is_video("Movie.2024.1080p.mkv")
    assert torbox.is_video("clip.MP4")
    assert not torbox.is_video("readme.txt")
    assert not torbox.is_video("")


def test_mylist_parses(monkeypatch):
    monkeypatch.setattr(torbox.config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(torbox, "get_json",
                        lambda *a, **k: {"success": True, "data": [{"id": 1, "name": "T", "files": []}]})
    assert torbox.mylist()[0]["id"] == 1


def test_mylist_bad_shape_is_empty(monkeypatch):
    monkeypatch.setattr(torbox.config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(torbox, "get_json", lambda *a, **k: {"data": None})
    assert torbox.mylist() == []


def test_mylist_swallows_errors(monkeypatch):
    monkeypatch.setattr(torbox.config, "torbox_token", lambda: "KEY")
    def boom(*a, **k):
        raise RuntimeError("api down")
    monkeypatch.setattr(torbox, "get_json", boom)
    assert torbox.mylist() == []


def test_video_files_filters():
    torrent = {"files": [{"name": "a.mkv"}, {"name": "b.nfo"}, {"short_name": "c.mp4"}]}
    got = [f.get("name") or f.get("short_name") for f in torbox.video_files(torrent)]
    assert got == ["a.mkv", "c.mp4"]


def test_get_torrent_by_id(monkeypatch):
    monkeypatch.setattr(torbox, "mylist", lambda: [{"id": 7, "name": "seven"}, {"id": 8}])
    assert torbox.get_torrent("7")["name"] == "seven"
    assert torbox.get_torrent(99) is None


def test_request_link_token_query_first(monkeypatch):
    monkeypatch.setattr(torbox.config, "torbox_token", lambda: "KEY")
    calls = []
    def fake(url, headers=None, **k):
        calls.append(url)
        return {"data": "https://cdn/stream.mkv"}
    monkeypatch.setattr(torbox, "get_json", fake)
    assert torbox.request_link(5, 2) == "https://cdn/stream.mkv"
    assert "token=KEY" in calls[0] and "torrent_id=5" in calls[0] and "file_id=2" in calls[0]


def test_request_link_empty_on_failure(monkeypatch):
    monkeypatch.setattr(torbox.config, "torbox_token", lambda: "KEY")
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(torbox, "get_json", boom)
    assert torbox.request_link(5, 2) == ""
