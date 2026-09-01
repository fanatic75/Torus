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


def test_torbox_list_empty_shows_message(kodi, monkeypatch):
    monkeypatch.setattr(main.config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(main.torbox, "mylist", lambda: [])
    main.torbox_list()
    assert len(kodi.items) == 1
    assert "action=noop" in kodi.items[0]["url"]


def test_torbox_list_skips_torrents_with_no_files(kodi, monkeypatch):
    monkeypatch.setattr(main.config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(main.torbox, "mylist",
                        lambda: [_torrent(1, "downloading", []),
                                 _torrent(2, "Movie", [{"id": 9, "name": "movie.mkv"}])])
    main.torbox_list()
    assert len(kodi.items) == 1   # the file-less torrent is skipped
    assert "torrent_id=2" in kodi.items[0]["url"]


# --- torbox_files ----------------------------------------------------------
def test_torbox_files_lists_all_files(kodi, monkeypatch):
    monkeypatch.setattr(main.torbox, "get_torrent",
                        lambda tid: _torrent(2, "Show", [{"id": 1, "name": "e1.mkv"},
                                                         {"id": 2, "name": "notes.nfo"},
                                                         {"id": 3, "short_name": "e2.mp4"}]))
    main.torbox_files("2")
    assert len(kodi.items) == 3   # nothing filtered — all files listed
    assert all("action=torbox_play" in it["url"] for it in kodi.items)
    assert [it["url"].count("file_id") for it in kodi.items] == [1, 1, 1]


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


# --- stop-current-on-new-pick (movie-switch bug) --------------------------
def test_fresh_movie_pick_stops_current(kodi):
    kodi.player["playing"] = True
    main._stop_current_if_switching("tt1", "movie", 0, 0)
    assert kodi.player["stopped"] == 1


def test_nothing_playing_no_stop(kodi):
    kodi.player["playing"] = False
    main._stop_current_if_switching("tt1", "movie", 0, 0)
    assert kodi.player["stopped"] == 0


def test_next_episode_advance_does_not_stop(kodi):
    # a genuine advance: we finished the prev episode (pos 0) and moved INTO the
    # queued S1E2 pointer at pos 1
    prev = "http://cdn/previous-episode.mkv"
    ptr = main.build_url(action="play", imdb="tt9", mtype="series", season=1, episode=2)
    kodi.playlist["items"] = [prev, ptr]
    kodi.playlist["pos"] = 1
    kodi.player["playing"] = True
    main._stop_current_if_switching("tt9", "series", 1, 2)
    assert kodi.player["stopped"] == 0   # advance -> keep flowing


def test_fresh_series_episode_pick_stops_current(kodi):
    # regression: a freshly-picked episode is at pos 0 and its path matches the
    # pointer we'd queue — must still be treated as a fresh pick and stop.
    ptr = main.build_url(action="play", imdb="tt9", mtype="series", season=1, episode=1)
    kodi.playlist["items"] = [ptr]
    kodi.playlist["pos"] = 0
    kodi.player["playing"] = True
    main._stop_current_if_switching("tt9", "series", 1, 1)
    assert kodi.player["stopped"] == 1   # pos 0 -> fresh pick -> stop


def test_fresh_series_pick_stops_current(kodi):
    # playlist holds a DIFFERENT show's pointer -> this pick isn't an advance
    other = main.build_url(action="play", imdb="ttX", mtype="series", season=3, episode=3)
    kodi.playlist["items"] = [other]
    kodi.playlist["pos"] = 0
    kodi.player["playing"] = True
    main._stop_current_if_switching("tt9", "series", 1, 1)
    assert kodi.player["stopped"] == 1


def test_play_movie_stops_current_then_resolves(kodi, monkeypatch):
    monkeypatch.setattr(main.config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(main.cinemeta, "meta", lambda *a, **k: {})
    monkeypatch.setattr(main.db, "get_progress", lambda *a, **k: None)
    kodi.player["playing"] = True
    main.play(imdb="tt1", mtype="movie", url="http://cdn/movie.mkv")
    assert kodi.player["stopped"] == 1
    assert kodi.resolved[-1]["ok"] is True
