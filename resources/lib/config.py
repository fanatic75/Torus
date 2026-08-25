"""Runtime configuration and credential storage.

Keeps the remote-control UX painless: metadata is keyless (Cinemeta), and TorBox
is linked via the in-addon device-code flow (see auth.py) — the returned token is
stored in a small file in the addon profile, never typed.
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


def profile_dir() -> str:
    """Writable per-user addon directory (Kodi profile, or a local dir in dev)."""
    if xbmcvfs is not None:
        path = xbmcvfs.translatePath("special://profile/addon_data/plugin.video.torus/")
    else:
        path = os.path.join(_REPO_ROOT, ".devprofile")
    os.makedirs(path, exist_ok=True)
    return path


# Back-compat alias.
_profile_dir = profile_dir


def get(key: str, default: str = "") -> str:
    """Kodi setting first, then dev.config.json, then default."""
    if _ADDON is not None:
        value = _ADDON.getSetting(key)
        if value:
            return value
    return _dev_config().get(key, default)


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
    return get("provider", "both")


def image_proxy() -> bool:
    """Route poster/backdrop images through a proxy so ISP-blocked image hosts
    (e.g. Cinemeta's image host behind Jio) still load in Kodi's image loader."""
    return get("image_proxy", "true").lower() != "false"


def prune_enabled() -> bool:
    """When off (default), resume points are kept forever (Continue Watching just
    shows the 40 most recent). When on, prune after `prune_days`."""
    return get("prune_enabled", "false").lower() == "true"


def prune_days() -> int:
    try:
        return max(1, int(get("prune_days", "365")))
    except (TypeError, ValueError):
        return 365
