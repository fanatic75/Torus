"""TorBox cloud library — your own files already on TorBox.

A fallback for when the indexers don't have something: browse what you've added
to your TorBox account and play it directly. Uses the main TorBox API with the
linked device-code token (Bearer). Playback links come from requestdl.
"""
from __future__ import annotations

from . import config
from .http import get_json

API = "https://api.torbox.app/v1/api"

_VIDEO_EXT = (".mkv", ".mp4", ".avi", ".m2ts", ".mov", ".wmv",
              ".flv", ".webm", ".ts", ".m4v", ".mpg", ".mpeg")


def is_video(name: str) -> bool:
    return (name or "").lower().endswith(_VIDEO_EXT)


def _bearer() -> dict:
    return {"Authorization": f"Bearer {config.torbox_token()}"}


def mylist() -> list[dict]:
    """The user's TorBox torrents, each carrying a `files` list."""
    try:
        data = get_json(f"{API}/torrents/mylist?bypass_cache=true",
                        headers=_bearer(), timeout=30).get("data")
    except Exception:  # noqa: BLE001 - network/API best-effort; caller shows empty
        return []
    return data if isinstance(data, list) else []


def get_torrent(torrent_id) -> dict | None:
    for torrent in mylist():
        if str(torrent.get("id")) == str(torrent_id):
            return torrent
    return None


def video_files(torrent: dict) -> list[dict]:
    return [f for f in (torrent.get("files") or [])
            if is_video(f.get("name") or f.get("short_name") or "")]


def request_link(torrent_id, file_id) -> str:
    """A directly-playable URL for one file in a TorBox torrent, or "" on failure.

    Tries the documented token-as-query auth first, then Bearer — so it works
    whichever the linked token expects.
    """
    token = config.torbox_token()
    base = f"{API}/torrents/requestdl?torrent_id={torrent_id}&file_id={file_id}"
    for url, headers in ((f"{base}&token={token}", None), (base, _bearer())):
        try:
            data = get_json(url, headers=headers).get("data")
            if isinstance(data, str) and data:
                return data
        except Exception:  # noqa: BLE001 - try the next auth style
            continue
    return ""
