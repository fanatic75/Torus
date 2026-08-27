from resources.lib import config


def test_get_precedence_and_default(monkeypatch):
    monkeypatch.setattr(config, "_DEV_CACHE", {"provider": "comet"})
    assert config.get("provider", "both") == "comet"
    assert config.get("missing", "fallback") == "fallback"


def test_provider_and_flag_parsing(monkeypatch):
    monkeypatch.setattr(config, "_DEV_CACHE",
                        {"provider": "torrentio", "image_proxy": "false",
                         "prune_enabled": "true", "prune_days": "10"})
    assert config.provider() == "torrentio"
    assert config.image_proxy() is False
    assert config.prune_enabled() is True
    assert config.prune_days() == 10


def test_flag_defaults(monkeypatch):
    monkeypatch.setattr(config, "_DEV_CACHE", {})
    assert config.provider() == "both"
    assert config.image_proxy() is True          # default on
    assert config.prune_enabled() is False        # default off
    assert config.prune_days() == 365


def test_prune_days_invalid_falls_back(monkeypatch):
    monkeypatch.setattr(config, "_DEV_CACHE", {"prune_days": "not-a-number"})
    assert config.prune_days() == 365


def test_torbox_token_override_wins(monkeypatch, tmp_profile):
    monkeypatch.setattr(config, "_DEV_CACHE", {"torbox_api_key": "OVERRIDE"})
    assert config.torbox_token() == "OVERRIDE"


def test_torbox_token_file_roundtrip(monkeypatch, tmp_profile):
    monkeypatch.setattr(config, "_DEV_CACHE", {})  # no override
    assert config.torbox_token() == ""
    config.set_torbox_token("tok123")
    assert config.torbox_token() == "tok123"
    config.clear_torbox_token()
    assert config.torbox_token() == ""
