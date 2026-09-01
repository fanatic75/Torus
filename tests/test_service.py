"""Background service: auto-retry the next source when playback fails to open."""
import json

import service


def _state(**over):
    s = {"imdb": "tt1", "mtype": "movie", "season": 0, "episode": 0,
         "url": "u0", "candidates": ["u0", "u1", "u2"], "cand_idx": 0}
    s.update(over)
    return s


def _fail(kodi, state):
    kodi.win[service.PLAYING_PROP] = json.dumps(state)
    service.TorusPlayer().onPlayBackError()


def test_retry_plays_next_source(kodi, monkeypatch):
    monkeypatch.setattr(service.db, "get_progress", lambda *a, **k: None)
    _fail(kodi, _state(cand_idx=0))
    assert kodi.player["played"] == ["u1"]                       # advanced to fallback #1
    assert json.loads(kodi.win[service.PLAYING_PROP])["cand_idx"] == 1


def test_retry_chains_through_fallbacks(kodi, monkeypatch):
    monkeypatch.setattr(service.db, "get_progress", lambda *a, **k: None)
    _fail(kodi, _state(cand_idx=1))                              # already on #1
    assert kodi.player["played"] == ["u2"]                       # -> #2
    assert json.loads(kodi.win[service.PLAYING_PROP])["cand_idx"] == 2


def test_retry_exhausted_gives_up(kodi, monkeypatch):
    monkeypatch.setattr(service.db, "get_progress", lambda *a, **k: None)
    _fail(kodi, _state(cand_idx=2))                              # last one already failed
    assert kodi.player["played"] == []                          # nothing more to try


def test_no_retry_without_candidates(kodi, monkeypatch):
    # a Choose-source play stores no candidates -> a failure must not retry
    monkeypatch.setattr(service.db, "get_progress", lambda *a, **k: None)
    kodi.win[service.PLAYING_PROP] = json.dumps({"imdb": "tt1", "mtype": "movie", "url": "u0"})
    service.TorusPlayer().onPlayBackError()
    assert kodi.player["played"] == []


def test_no_retry_when_nothing_playing(kodi):
    # no PLAYING_PROP at all (e.g. user stopped) -> no retry
    service.TorusPlayer().onPlayBackError()
    assert kodi.player["played"] == []


def test_retry_carries_resume_point(kodi, monkeypatch):
    monkeypatch.setattr(service.db, "get_progress",
                        lambda *a, **k: {"position": 300, "duration": 1000, "url": ""})
    _fail(kodi, _state(cand_idx=0))
    assert kodi.player["played"] == ["u1"]
    item = kodi.player["played_items"][0]
    assert item.getProperty("ResumeTime") == "290.0"            # 300 - 10s rewind
    assert item.getProperty("TotalTime") == "1000.0"


def test_retry_series_requeues_next_episode(kodi, monkeypatch):
    # a retried episode must re-queue the next-episode pointer so autoplay-next / ⏭
    # still work (self.play replaces the playlist and wipes the original pointer)
    monkeypatch.setattr(service.db, "get_progress", lambda *a, **k: None)
    monkeypatch.setattr(service.cinemeta, "next_episode",
                        lambda imdb, s, e: {"imdb": "tt9", "season": 1, "episode": 2,
                                            "name": "Ep2", "poster": ""})
    kodi.win[service.PLAYING_PROP] = json.dumps(
        {"imdb": "tt9", "mtype": "series", "season": 1, "episode": 1,
         "candidates": ["u0", "u1"], "cand_idx": 0})
    service.TorusPlayer().onPlayBackError()
    assert kodi.player["played"] == ["u1"]                       # retried the next source
    assert any("action=play" in p and "episode=2" in p and "imdb=tt9" in p
               for p in kodi.playlist["items"])                  # next episode re-queued


def test_retry_movie_does_not_requeue(kodi, monkeypatch):
    monkeypatch.setattr(service.db, "get_progress", lambda *a, **k: None)
    kodi.win[service.PLAYING_PROP] = json.dumps(
        {"imdb": "tt1", "mtype": "movie", "candidates": ["u0", "u1"], "cand_idx": 0})
    service.TorusPlayer().onPlayBackError()
    assert kodi.player["played"] == ["u1"]
    assert kodi.playlist["items"] == []                          # movies have no next episode
