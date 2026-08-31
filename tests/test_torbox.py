"""TorBox cloud-library API module."""
from resources.lib import torbox


def test_files_returns_all_unfiltered():
    torrent = {"files": [{"name": "a.mkv"}, {"name": "b.nfo"}, {"short_name": "c.mp4"}]}
    assert torbox.files(torrent) == torrent["files"]   # nothing hidden
    assert torbox.files({}) == []                       # missing files key -> []


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


def test_request_link_falls_back_to_bearer(monkeypatch):
    monkeypatch.setattr(torbox.config, "torbox_token", lambda: "KEY")
    seen = []
    def fake(url, headers=None, **k):
        seen.append("token=" in url)
        return {"data": None} if "token=" in url else {"data": "https://cdn/from-bearer"}
    monkeypatch.setattr(torbox, "get_json", fake)
    assert torbox.request_link(1, 1) == "https://cdn/from-bearer"
    assert seen == [True, False]   # tried token-query, then fell back to Bearer


def test_request_link_both_styles_empty(monkeypatch):
    monkeypatch.setattr(torbox.config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(torbox, "get_json", lambda *a, **k: {"data": None})
    assert torbox.request_link(1, 1) == ""
