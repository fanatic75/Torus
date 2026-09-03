"""End-to-end simulation of native autoplay-next (the 1-ahead pointer chain)
from EVERY entry point that can start a series episode.

Autoplay-next is emergent: a launch path must put the episode into
PLAYLIST_VIDEO, play() must queue a lazy next-episode pointer after it, and Kodi
must advance the playlist at end-of-file — re-invoking play() for the pointer,
which queues the one after it, endlessly.

Kodi's EOF advance is the only part we can't run headless, so we SIMULATE it
(_run_playlist_to_end): drive play() for the current item, move the position
forward, drive play() again — exactly as Kodi would.

Entry points a series episode can start from:
  1. Continue Watching  → cw_menu → _play_via_playlist (WE seed the playlist)
  2. Episode page Play   → IsPlayable action=play (no url; fresh auto-pick)
  3. Choose source       → IsPlayable action=play&url=<src> (a specific source)
  4. The next-ep pointer → the chain continuation itself

For 1 we drive the real launch code. For 2/3 the click-that-seeds-the-playlist
is Kodi's job, so we model it by seeding PLAYLIST_VIDEO with the launch item
(the contract tests below assert those items ARE IsPlayable action=play, i.e.
that Kodi WILL play them through the playlist) and then verify the chain queues
and continues for that param shape.
"""
from urllib.parse import parse_qsl

import main
from resources.lib.providers.base import Stream

# Silicon-Valley-style 3-episode season used across the chain tests.
SEASON3 = {
    (3, 1): {"imdb": "tt1", "season": 3, "episode": 2, "name": "E2"},
    (3, 2): {"imdb": "tt1", "season": 3, "episode": 3, "name": "E3"},
    (3, 3): None,  # season end
}


def _dialog_choosing(monkeypatch, choice):
    monkeypatch.setattr(main.xbmcgui, "Dialog",
                        lambda: type("D", (), {"contextmenu": lambda s, x: choice})())


def _mock_playback(monkeypatch, next_chain):
    """Mock ONLY the external boundaries; play() and _queue_next_episode run for
    real. `next_chain` maps (season, episode) -> next-episode dict (or None)."""
    monkeypatch.setattr(main.config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(main.cinemeta, "meta", lambda *a, **k: {})
    monkeypatch.setattr(main.db, "get_progress", lambda *a, **k: None)
    monkeypatch.setattr(
        main, "_resolve_ranked",
        lambda imdb, mt, s, e, expected="": [Stream(f"Show.S{s:02d}E{e:02d}",
                                                    f"http://cdn/{s}x{e}.mkv", raw_name="x")])
    monkeypatch.setattr(main.cinemeta, "next_episode",
                        lambda imdb, s, e: next_chain.get((s, e)))


def _seed_launch(kodi, imdb, season, episode, url=None):
    """Model Kodi placing a clicked IsPlayable item into PLAYLIST_VIDEO at pos 0
    (what the episode-page / choose-source launches rely on)."""
    kw = dict(action="play", imdb=imdb, mtype="series", season=season, episode=episode)
    if url:
        kw["url"] = url
    kodi.playlist["items"] = [main.build_url(**kw)]
    kodi.playlist["pos"] = 0


def _run_playlist_to_end(kodi):
    """Play PLAYLIST_VIDEO to the end as Kodi would: resolve the current item via
    play(), then advance to whatever got queued after it. Returns the (season,
    episode) pairs played, in order, plus the queued pointer URLs seen."""
    played, pointers, guard = [], [], 0
    while 0 <= kodi.playlist["pos"] < len(kodi.playlist["items"]) and guard < 50:
        guard += 1
        pos = kodi.playlist["pos"]
        url = kodi.playlist["items"][pos]
        q = dict(parse_qsl(url.split("?", 1)[1]))
        pointers.append(url)
        kodi.player["playing"] = True
        main.play(imdb=q["imdb"], mtype=q.get("mtype", "series"),
                  season_number=int(q.get("season", 0)),
                  episode_number=int(q.get("episode", 0)), url=q.get("url"))
        played.append((int(q.get("season", 0)), int(q.get("episode", 0))))
        if pos + 1 < len(kodi.playlist["items"]):
            kodi.playlist["pos"] = pos + 1   # Kodi advances at EOF
        else:
            break                            # nothing queued after → chain ends
    return played, pointers


# --- the chain from every entry point --------------------------------------
def test_autoplay_from_continue_watching(kodi, tmp_profile, monkeypatch):
    _mock_playback(monkeypatch, SEASON3)
    _dialog_choosing(monkeypatch, 0)  # "Play"
    main.cw_menu("tt1", "series", 3, 1)   # real launch code seeds the playlist
    assert kodi.playlist["items"], "Continue Watching Play did not seed PLAYLIST_VIDEO"
    played, _ = _run_playlist_to_end(kodi)
    assert played == [(3, 1), (3, 2), (3, 3)]


def test_autoplay_from_episode_page(kodi, tmp_profile, monkeypatch):
    # Episode-page Play button: action=play, NO url (fresh auto-pick).
    _mock_playback(monkeypatch, SEASON3)
    _seed_launch(kodi, "tt1", 3, 1, url=None)
    played, _ = _run_playlist_to_end(kodi)
    assert played == [(3, 1), (3, 2), (3, 3)], "autoplay chain broke from the episode page"


def test_autoplay_from_choose_source(kodi, tmp_profile, monkeypatch):
    # Choose source: the FIRST episode plays a specific url; the chain must STILL
    # continue, and each queued pointer must be url-free (resolved fresh, never a
    # reused IP/time-locked TorBox link).
    _mock_playback(monkeypatch, SEASON3)
    _seed_launch(kodi, "tt1", 3, 1, url="http://cdn/picked-source.mkv")
    played, pointers = _run_playlist_to_end(kodi)
    assert played == [(3, 1), (3, 2), (3, 3)], "autoplay chain broke from Choose source"
    # only the first (hand-picked) item carries a url; every queued pointer is fresh
    assert not any("url=" in p for p in pointers[1:])


def test_movie_from_continue_watching_queues_nothing(kodi, tmp_profile, monkeypatch):
    _mock_playback(monkeypatch, {})
    _dialog_choosing(monkeypatch, 0)  # "Play"
    main.cw_menu("tt9", "movie", 0, 0)
    assert kodi.playlist["items"], "movie not queued into the playlist"
    q = dict(parse_qsl(kodi.playlist["items"][0].split("?", 1)[1]))
    kodi.playlist["pos"] = 0
    main.play(imdb=q["imdb"], mtype="movie", url=q.get("url"))
    # a movie must not queue a phantom next-episode pointer
    assert len(kodi.playlist["items"]) == 1


def test_last_episode_ends_the_chain(kodi, tmp_profile, monkeypatch):
    _mock_playback(monkeypatch, {(3, 3): None})  # E3 is the finale
    _seed_launch(kodi, "tt1", 3, 3, url=None)
    played, _ = _run_playlist_to_end(kodi)
    assert played == [(3, 3)]   # nothing queued after the last episode


# --- contract tests: each entry point builds a playlist-playable item ------
# These guard the assumption the chain tests rely on for the Kodi-native paths:
# if a launch item stops being `IsPlayable action=play`, Kodi won't play it
# through PLAYLIST_VIDEO and autoplay-next dies (exactly the PlayMedia regression,
# one level up).
def test_continue_watching_play_uses_playlist_not_playmedia(kodi, tmp_profile, monkeypatch):
    _mock_playback(monkeypatch, SEASON3)
    calls = []
    monkeypatch.setattr(main.xbmc, "executebuiltin", lambda c, *a, **k: calls.append(c))
    _dialog_choosing(monkeypatch, 0)
    main.cw_menu("tt1", "series", 3, 1)
    assert not any(c.startswith("PlayMedia(") for c in calls)   # never PlayMedia
    assert kodi.player["played"], "did not launch via Player().play(playlist)"
    assert "episode=1" in kodi.playlist["items"][0]


def test_episode_page_play_item_is_playable_action_play(kodi, monkeypatch):
    monkeypatch.setattr(main.cinemeta, "meta", lambda *a, **k: {
        "name": "Show", "videos": [{"season": 3, "episode": 1, "name": "E1"}]})
    main.episode("tt1", 3, 1)
    play = [it for it in kodi.items if "action=play" in it["url"]]
    assert play, "episode page has no Play item"
    assert play[0]["item"].getProperty("IsPlayable") == "true"
    assert "url=" not in play[0]["url"]        # fresh auto-pick, resolved on click


def test_sources_items_are_playable_action_play(kodi, monkeypatch):
    monkeypatch.setattr(main.config, "torbox_token", lambda: "KEY")
    monkeypatch.setattr(main.cinemeta, "meta", lambda *a, **k: {"name": "Show"})
    monkeypatch.setattr(main.providers, "get_provider", lambda: type(
        "P", (), {"search": lambda self, *a, **k: [Stream("rel", "http://src", raw_name="rel")]})())
    monkeypatch.setattr(main.ranking, "rank", lambda streams, **k: list(streams))
    main.sources("tt1", "series", 3, 1)
    play = [it for it in kodi.items if "action=play" in it["url"]]
    assert play, "Choose source produced no playable items"
    assert play[0]["item"].getProperty("IsPlayable") == "true"
    assert "url=" in play[0]["url"]            # a specific hand-picked source


def test_next_episode_pointer_is_playable_and_url_free(kodi):
    url, li = main._episode_pointer_item(
        {"imdb": "tt1", "season": 3, "episode": 2, "name": "E2"})
    assert li.getProperty("IsPlayable") == "true"
    assert "action=play" in url and "url=" not in url


def test_movie_detail_play_item_is_playable_action_play(kodi, monkeypatch):
    monkeypatch.setattr(main.cinemeta, "meta", lambda *a, **k: {"name": "Movie", "poster": ""})
    monkeypatch.setattr(main.db, "in_watchlist", lambda imdb: False)
    main.detail("tt1", "movie")
    play = [it for it in kodi.items if "action=play" in it["url"]]
    assert play, "movie detail has no Play item"
    assert play[0]["item"].getProperty("IsPlayable") == "true"
    assert "url=" not in play[0]["url"]        # fresh auto-pick on click
