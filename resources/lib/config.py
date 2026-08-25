"""Runtime configuration and credential storage.

Two principles that keep the remote-control UX painless:
  * TMDB uses a bundled key (a low-value, rate-limited client id) so users never
    type one. It's overridable via the optional `tmdb_api_key` setting.
  * TorBox is linked via the in-addon device-code flow (see auth.py); the returned
    token is stored in a small file in the addon profile — never typed.
"""
import json
import os

try:
    import xbmcaddon
    import xbmcvfs

    _ADDON = xbmcaddon.Addon()
except Exception:  # not running inside Kodi (laptop dev)
    _ADDON = None
    xbmcvfs = None

# Bundled TMDB v3 API key. NOT a personal secret — it's a client identifier that
# TMDB permits embedding in apps. Overridable via settings; rotate freely.
DEFAULT_TMDB_KEY = ""

_DEV_CACHE = None
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _dev_config() -> dict:
    global _DEV_CACHE
    if _DEV_CACHE is None:
        try:
            with open(os.path.join(_REPO_ROOT, "dev.config.json"), encoding="utf-8") as fh:
                _DEV_CACHE = json.load(fh)
        except Exception:
            _DEV_CACHE = {}
    return _DEV_CACHE


def _profile_dir() -> str:
    """Writable per-user addon directory (Kodi profile, or a local dir in dev)."""
    if xbmcvfs is not None:
        path = xbmcvfs.translatePath("special://profile/addon_data/plugin.video.torus/")
    else:
        path = os.path.join(_REPO_ROOT, ".devprofile")
    os.makedirs(path, exist_ok=True)
    return path


def get(key: str, default: str = "") -> str:
    """Kodi setting first, then dev.config.json, then default."""
    if _ADDON is not None:
        value = _ADDON.getSetting(key)
        if value:
            return value
    return _dev_config().get(key, default)


# --- TMDB ------------------------------------------------------------------
def tmdb_key() -> str:
    return get("tmdb_api_key") or DEFAULT_TMDB_KEY


# --- TorBox token (stored, not typed) --------------------------------------
def _token_path() -> str:
    return os.path.join(_profile_dir(), "torbox_token.json")


def torbox_token() -> str:
    # Explicit setting/dev override wins (handy for testing); else the linked token.
    override = get("torbox_api_key")
    if override:
        return override
    try:
        with open(_token_path(), encoding="utf-8") as fh:
            return json.load(fh).get("token", "")
    except Exception:
        return ""


def set_torbox_token(token: str) -> None:
    with open(_token_path(), "w", encoding="utf-8") as fh:
        json.dump({"token": token}, fh)


def clear_torbox_token() -> None:
    try:
        os.remove(_token_path())
    except Exception:
        pass


# --- other settings --------------------------------------------------------
def provider() -> str:
    return get("provider", "comet")


def quality_profile() -> str:
    return get("quality_profile", "cinephile")
