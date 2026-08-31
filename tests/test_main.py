"""Router/handler behaviour — now testable because main.py is import-safe.

Focus: the TorBox Cloud handlers (single-vs-multi file, empty states, and the
torus.playing clear that stops the resume engine mis-saving cloud playback)."""
import main


def _torrent(tid, name, files):
    return {"id": tid, "name": name, "files": files}


# --- torbox_list -----------------------------------------------------------
def test_torbox_list_requires_token(kodi, monkeypatch):
    monkeypatch.setattr(main.config, "torbox_token", lambda: "")
    main.torbox_list()
    assert kodi.items == []


def test_torbox_list_single_file_is_playable(kodi, monkeypatch):
    monkeypatch.setattr(main.config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(main.torbox, "mylist",
                        lambda: [_torrent(1, "Movie", [{"id": 5, "name": "movie.mkv"}])])
    main.torbox_list()
    assert len(kodi.items) == 1
    it = kodi.items[0]
    assert it["folder"] is False
    assert "action=torbox_play" in it["url"]
    assert "torrent_id=1" in it["url"] and "file_id=5" in it["url"]


def test_torbox_list_multifile_is_folder(kodi, monkeypatch):
    monkeypatch.setattr(main.config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(main.torbox, "mylist",
                        lambda: [_torrent(2, "Show", [{"id": 1, "name": "e1.mkv"},
                                                      {"id": 2, "name": "e2.mkv"}])])
    main.torbox_list()
    it = kodi.items[0]
    assert it["folder"] is True
    assert "action=torbox_files" in it["url"] and "torrent_id=2" in it["url"]


def test_torbox_list_novideo_shows_message(kodi, monkeypatch):
    monkeypatch.setattr(main.config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(main.torbox, "mylist",
                        lambda: [_torrent(3, "Junk", [{"id": 1, "name": "readme.txt"}])])
    main.torbox_list()
    assert len(kodi.items) == 1
    assert "action=noop" in kodi.items[0]["url"]


# --- torbox_files ----------------------------------------------------------
def test_torbox_files_lists_only_videos(kodi, monkeypatch):
    monkeypatch.setattr(main.torbox, "get_torrent",
                        lambda tid: _torrent(2, "Show", [{"id": 1, "name": "e1.mkv"},
                                                         {"id": 2, "name": "notes.nfo"},
                                                         {"id": 3, "short_name": "e2.mp4"}]))
    main.torbox_files("2")
    assert len(kodi.items) == 2
    assert all("action=torbox_play" in it["url"] for it in kodi.items)
    assert "file_id=1" in kodi.items[0]["url"] and "file_id=3" in kodi.items[1]["url"]


def test_torbox_files_not_found(kodi, monkeypatch):
    monkeypatch.setattr(main.torbox, "get_torrent", lambda tid: None)
    main.torbox_files("999")
    assert kodi.items == []


# --- torbox_play -----------------------------------------------------------
def test_torbox_play_success_clears_playing_prop(kodi, monkeypatch):
    monkeypatch.setattr(main.config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(main.torbox, "request_link", lambda t, f: "https://cdn/stream.mkv")
    kodi.win[main.PLAYING_PROP] = "stale-movie-identity"   # left over from a prior play()
    main.torbox_play("1", "5")
    assert main.PLAYING_PROP not in kodi.win               # cleared -> service won't mis-save
    assert kodi.resolved[-1]["ok"] is True
    assert kodi.resolved[-1]["item"].getPath() == "https://cdn/stream.mkv"


def test_torbox_play_dead_link_fails(kodi, monkeypatch):
    monkeypatch.setattr(main.config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(main.torbox, "request_link", lambda t, f: "")
    main.torbox_play("1", "5")
    assert kodi.resolved[-1]["ok"] is False


def test_torbox_play_requires_token(kodi, monkeypatch):
    monkeypatch.setattr(main.config, "torbox_token", lambda: "")
    main.torbox_play("1", "5")
    assert kodi.resolved[-1]["ok"] is False
