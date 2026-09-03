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


# --- Continue Watching popover (cw_menu) ----------------------------------
def test_continue_watching_opens_popover_not_direct_play(kodi, monkeypatch):
    monkeypatch.setattr(main.db, "list_continue", lambda: [
        {"imdb": "tt1", "mtype": "movie", "name": "Movie", "poster": "p.jpg"}])
    main.continue_watching()
    it = kodi.items[-1]
    assert it["folder"] is False
    assert "action=cw_menu" in it["url"]          # click opens the popover
    assert "action=play" not in it["url"]         # not a one-click resolve
    assert it["item"].getProperty("IsPlayable") == ""  # no direct playback


def _capture_builtins(monkeypatch):
    calls = []
    monkeypatch.setattr(main.xbmc, "executebuiltin", lambda cmd, *a, **k: calls.append(cmd))
    return calls


def _dialog_returning(monkeypatch, choice):
    class _D:
        def contextmenu(self, *a, **k): return choice
    monkeypatch.setattr(main.xbmcgui, "Dialog", lambda: _D())


def test_cw_menu_play_launches_via_playlist_for_autoplay_next(kodi, monkeypatch):
    # REGRESSION: Play must launch through PLAYLIST_VIDEO, not PlayMedia — a lone
    # PlayMedia item sits outside the playlist so the queued next-episode pointer
    # never auto-advances (autoplay-next silently breaks from Continue Watching).
    calls = _capture_builtins(monkeypatch)
    _dialog_returning(monkeypatch, 0)  # "Play"
    main.cw_menu("tt1", "series", 2, 5)
    assert not any(c.startswith("PlayMedia(") for c in calls)   # never PlayMedia
    # the current episode is seeded into the video playlist and Player().play()'d
    assert kodi.playlist["items"], "episode not queued into PLAYLIST_VIDEO"
    ptr = kodi.playlist["items"][0]
    assert "action=play" in ptr and "imdb=tt1" in ptr
    assert "season=2" in ptr and "episode=5" in ptr
    assert kodi.player["played"], "Player().play() was not called"


def test_cw_menu_choose_source_opens_source_list(kodi, monkeypatch):
    calls = _capture_builtins(monkeypatch)
    _dialog_returning(monkeypatch, 1)  # "Choose source"
    main.cw_menu("tt1", "movie", 0, 0)
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd.startswith("Container.Update(")
    assert "action=sources" in cmd and "imdb=tt1" in cmd


def test_cw_menu_cancel_does_nothing(kodi, monkeypatch):
    calls = _capture_builtins(monkeypatch)
    _dialog_returning(monkeypatch, -1)  # dismissed
    main.cw_menu("tt1", "movie", 0, 0)
    assert calls == []


# --- My List: manage buttons, reorder (grab & place), pin -----------------
def _urls(kodi):
    return [it["url"] for it in kodi.items]


def test_watchlist_shows_single_options_row(kodi, tmp_profile):
    main.db.add_watchlist("tt1", "movie", "M", "", None)
    main.watchlist()
    urls = " ".join(_urls(kodi))
    assert "action=wl_options" in urls               # one entry point
    # reorder/pin are behind the popover, not direct rows
    assert "action=wl_reorder" not in urls and "action=wl_pinmode" not in urls


def test_empty_watchlist_offers_new_folder_not_options(kodi, tmp_profile):
    main.watchlist()
    urls = " ".join(_urls(kodi))
    assert "action=wl_newfolder" in urls
    assert "action=wl_options" not in urls


def test_watchlist_unified_order_folder_between_titles(kodi, tmp_profile):
    main.db.add_watchlist("a", "movie", "A", "", None)
    fid = main.db.create_folder("Fold")
    main.db.add_watchlist("b", "movie", "B", "", None)
    main.db.set_root_order(["t:b", f"f:{fid}", "t:a"])   # folder wedged between titles
    main.watchlist()
    # rows after the Options row, in unified order
    urls = [u for u in _urls(kodi) if "wl_options" not in u]
    assert urls[0].endswith("imdb=b") or "imdb=b" in urls[0]
    assert f"folder={fid}" in urls[1]                     # folder in the middle
    assert "imdb=a" in urls[2]


def test_options_root_newfolder_dispatch(kodi, tmp_profile, monkeypatch):
    main.db.add_watchlist("tt1", "movie", "M", "", None)
    picked = {}
    monkeypatch.setattr(main.xbmcgui, "Dialog",
                        lambda: type("D", (), {"contextmenu": lambda s, x: 0})())  # New folder
    monkeypatch.setattr(main, "wl_newfolder", lambda: picked.setdefault("nf", True))
    main.wl_options(None)
    assert picked.get("nf") is True


def test_options_folder_reorder_dispatch(kodi, tmp_profile, monkeypatch):
    fid = main.db.create_folder("F")
    calls = []
    monkeypatch.setattr(main.xbmc, "executebuiltin", lambda c, *a, **k: calls.append(c))
    monkeypatch.setattr(main.xbmcgui, "Dialog",
                        lambda: type("D", (), {"contextmenu": lambda s, x: 0})())  # Reorder
    main.wl_options(fid)
    assert any("Container.Update" in c and "action=wl_reorder" in c and f"folder={fid}" in c
               for c in calls)


def test_reorder_screen_rows_are_grabbable_when_idle(kodi, tmp_profile):
    for i in (1, 2):
        main.db.add_watchlist(f"tt{i}", "movie", f"M{i}", "", None)
    main.wl_reorder(None)
    urls = _urls(kodi)
    assert any("action=wl_reorder_done" in u for u in urls)   # Done row
    assert sum("action=wl_grab" in u and "grabcancel" not in u for u in urls) == 2


def test_grab_sets_state_then_rows_become_drop_targets(kodi, tmp_profile):
    for i in (1, 2, 3):
        main.db.add_watchlist(f"tt{i}", "movie", f"M{i}", "", None)
    main.wl_grab("t:tt2", None)
    assert kodi.win[main.REORDER_PROP] == "t:tt2"
    main.wl_reorder(None)
    urls = _urls(kodi)
    assert any("action=wl_grabcancel" in u for u in urls)         # the held row
    assert any("before=__bottom__" in u for u in urls)            # bottom target
    assert sum("action=wl_drop" in u for u in urls) == 3          # 2 rows + bottom


def test_drop_reorders_title_before_target(kodi, tmp_profile):
    for i in (1, 2, 3):
        main.db.add_watchlist(f"tt{i}", "movie", f"M{i}", "", None)
    # display order is tt3, tt2, tt1 (newest first). Grab tt1, drop before tt3 (top).
    main.wl_grab("t:tt1", None)
    main.wl_drop("t:tt3", None)
    assert [r["imdb"] for r in main.db.list_watchlist()] == ["tt1", "tt3", "tt2"]
    assert kodi.win.get(main.REORDER_PROP, "") == ""             # grab cleared


def test_drop_to_bottom(kodi, tmp_profile):
    for i in (1, 2, 3):
        main.db.add_watchlist(f"tt{i}", "movie", f"M{i}", "", None)
    main.wl_grab("t:tt3", None)          # tt3 is currently at the top
    main.wl_drop("__bottom__", None)
    assert [r["imdb"] for r in main.db.list_watchlist()] == ["tt2", "tt1", "tt3"]


def test_drop_interleaves_folder_and_title(kodi, tmp_profile):
    main.db.add_watchlist("a", "movie", "A", "", None)
    fid = main.db.create_folder("Fold")
    main.db.add_watchlist("b", "movie", "B", "", None)
    # unified root starts b, folder, a (newest on top). Grab the folder, drop at bottom.
    main.wl_grab(f"f:{fid}", None)
    main.wl_drop("__bottom__", None)
    assert [e["key"] for e in main.db.list_root_entries()] == ["t:b", "t:a", f"f:{fid}"]


def test_drop_moves_title_below_a_folder(kodi, tmp_profile):
    main.db.add_watchlist("a", "movie", "A", "", None)
    fid = main.db.create_folder("Fold")     # root: folder, a
    main.wl_grab("t:a", None)               # move title a above the folder
    main.wl_drop(f"f:{fid}", None)
    assert [e["key"] for e in main.db.list_root_entries()] == ["t:a", f"f:{fid}"]


def test_grabcancel_clears_state(kodi, tmp_profile):
    main.db.add_watchlist("tt1", "movie", "M", "", None)
    main.wl_grab("t:tt1", None)
    main.wl_grabcancel(None)
    assert kodi.win.get(main.REORDER_PROP, "") == ""


def test_entering_watchlist_clears_stale_grab(kodi, tmp_profile):
    main.db.add_watchlist("tt1", "movie", "M", "", None)
    kodi.win[main.REORDER_PROP] = "t:tt1"
    main.watchlist()
    assert kodi.win.get(main.REORDER_PROP, "") == ""


def test_pinmode_lists_toggles_and_toggle_flips(kodi, tmp_profile):
    main.db.add_watchlist("tt1", "movie", "M1", "", None)
    main.wl_pinmode(None)
    urls = _urls(kodi)
    assert any("action=wl_pinmode_done" in u for u in urls)
    assert any("action=wl_pintoggle" in u and "key=t" in u for u in urls)  # key-based
    main.wl_pintoggle("t:tt1", None)
    assert main.db.is_pinned("tt1") is True
    main.wl_pintoggle("t:tt1", None)
    assert main.db.is_pinned("tt1") is False


def test_pinmode_can_pin_a_folder(kodi, tmp_profile):
    fid = main.db.create_folder("Fold")
    main.wl_pinmode(None)                      # root pin screen lists the folder
    assert any(f"key=f" in u for u in _urls(kodi))
    main.wl_pintoggle(f"f:{fid}", None)
    assert main.db.is_folder_pinned(fid) is True


def test_pin_anchors_title_when_new_one_added(kodi, tmp_profile):
    # end-to-end through the handlers: pin holds its slot as a new title arrives
    for i in (1, 2, 3):
        main.db.add_watchlist(f"tt{i}", "movie", f"M{i}", "", None)   # tt3, tt2, tt1
    main.wl_pintoggle("t:tt3", None)          # pin the top one
    main.db.add_watchlist("tt4", "movie", "M4", "", None)
    assert [r["imdb"] for r in main.db.list_watchlist()] == ["tt3", "tt4", "tt2", "tt1"]


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


def test_play_stashes_fallback_candidates(kodi, monkeypatch):
    monkeypatch.setattr(main.config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(main.cinemeta, "meta", lambda *a, **k: {})
    monkeypatch.setattr(main.db, "get_progress", lambda *a, **k: None)
    from resources.lib.providers.base import Stream
    ranked = [Stream("A", "http://u0", raw_name="A"),
              Stream("B", "http://u1", raw_name="B"),
              Stream("C", "http://u2", raw_name="C"),
              Stream("D", "http://u3", raw_name="D")]
    monkeypatch.setattr(main, "_resolve_ranked", lambda *a, **k: ranked)
    main.play(imdb="tt1", mtype="movie")   # auto-pick (no url)
    import json
    state = json.loads(kodi.win[main.PLAYING_PROP])
    assert state["url"] == "http://u0"                       # top played
    assert state["candidates"] == ["http://u0", "http://u1", "http://u2"]  # top 3 kept
    assert state["cand_idx"] == 0
    assert kodi.resolved[-1]["ok"] is True
