from resources.lib import cinemeta, config

_META = {
    "name": "Show",
    "poster": "http://img/poster.jpg",
    "videos": [
        {"season": 1, "episode": 1}, {"season": 1, "episode": 2},
        {"season": 2, "episode": 1},
        {"season": 0, "episode": 1},  # special — must be ignored
    ],
}


def test_next_episode_within_season(monkeypatch):
    monkeypatch.setattr(cinemeta, "meta", lambda *a, **k: _META)
    nxt = cinemeta.next_episode("tt1", 1, 1)
    assert (nxt["season"], nxt["episode"]) == (1, 2)


def test_next_episode_crosses_season(monkeypatch):
    monkeypatch.setattr(cinemeta, "meta", lambda *a, **k: _META)
    nxt = cinemeta.next_episode("tt1", 1, 2)
    assert (nxt["season"], nxt["episode"]) == (2, 1)


def test_next_episode_none_after_last(monkeypatch):
    monkeypatch.setattr(cinemeta, "meta", lambda *a, **k: _META)
    assert cinemeta.next_episode("tt1", 2, 1) is None


def test_next_episode_ignores_specials(monkeypatch):
    monkeypatch.setattr(cinemeta, "meta", lambda *a, **k: _META)
    # from S2E1 there is no non-special episode after it, despite S0E1 existing
    assert cinemeta.next_episode("tt1", 2, 1) is None


def test_image_proxy_toggle(monkeypatch):
    monkeypatch.setattr(config, "image_proxy", lambda: False)
    assert cinemeta.image("http://host/a.jpg") == "http://host/a.jpg"
    monkeypatch.setattr(config, "image_proxy", lambda: True)
    proxied = cinemeta.image("http://host/a.jpg")
    assert "images.weserv.nl" in proxied
    assert cinemeta.image("") == ""
