"""Runtime configuration.

Reads settings from Kodi (addon settings the user fills in) when running inside
Kodi, and falls back to a gitignored dev.config.json when running outside Kodi
(e.g. testing modules on a laptop). Real users always go through Kodi settings;
dev.config.json is never deployed or committed.
"""
import json
import os

try:
    import xbmcaddon

    _ADDON = xbmcaddon.Addon()
except Exception:  # not running inside Kodi
    _ADDON = None

_DEV_CACHE = None


def _dev_config() -> dict:
    """Load dev.config.json from the repo root, once."""
    global _DEV_CACHE
    if _DEV_CACHE is None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        try:
            with open(os.path.join(root, "dev.config.json"), encoding="utf-8") as fh:
                _DEV_CACHE = json.load(fh)
        except Exception:
            _DEV_CACHE = {}
    return _DEV_CACHE


def get(key: str, default: str = "") -> str:
    """Kodi setting first, then dev.config.json, then default."""
    if _ADDON is not None:
        value = _ADDON.getSetting(key)
        if value:
            return value
    return _dev_config().get(key, default)


def tmdb_key() -> str:
    return get("tmdb_api_key")


def torbox_key() -> str:
    return get("torbox_api_key")


def provider() -> str:
    return get("provider", "comet")


def quality_profile() -> str:
    return get("quality_profile", "cinephile")
