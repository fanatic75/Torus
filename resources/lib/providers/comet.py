"""Comet provider — Stremio-protocol source discovery via a Comet instance.

Comet takes a base64(JSON) config with the user's TorBox key and returns cached,
already-resolved streams for an IMDb id. Its stream `url` is a Comet playback
link that redirects to the actual TorBox stream, so it's handed straight to Kodi.
"""

from __future__ import annotations
import base64
import json
import re

from ..http import get_json
from .base import Provider, Stream

DEFAULT_HOST = "https://comet.elfhosted.com"

_RES_MAP = [("2160p", ("2160", "4k", "uhd")),
            ("1080p", ("1080",)),
            ("720p", ("720",)),
            ("480p", ("480", "sd"))]


def _quality(text: str) -> str:
    low = text.lower()
    for label, needles in _RES_MAP:
        if any(n in low for n in needles):
            return label
    return ""


def _release_title(description: str) -> str:
    if not description:
        return ""
    match = re.search(r"\U0001F4C4\s*(.+)", description)  # text after the 📄 marker
    candidate = match.group(1) if match else description.splitlines()[0]
    # cut at the next emoji annotation (📹 codec, 🔊 audio, 👤 seeders, 💾 size, …)
    return re.split(r"[\U0001F300-\U0001FAFF]", candidate)[0].strip()


def _size(description: str) -> str:
    match = re.search(r"([\d.]+\s*[GMK]B)", description or "", re.IGNORECASE)
    return match.group(1) if match else ""


def _seeders(description: str) -> int | None:
    match = re.search(r"\U0001F464\s*(\d+)", description or "")  # 👤 N
    return int(match.group(1)) if match else None


class CometProvider(Provider):
    def __init__(self, torbox_key: str, host: str = DEFAULT_HOST,
                 cached_only: bool = True):
        self.key = torbox_key
        self.host = host.rstrip("/")
        self.cached_only = cached_only

    def _config_segment(self) -> str:
        config = {
            "debridService": "torbox",
            "debridApiKey": self.key,
            "cachedOnly": self.cached_only,
        }
        return base64.b64encode(json.dumps(config).encode()).decode()

    @staticmethod
    def _stream_id(imdb_id: str, media_type: str,
                   season: int | None, episode: int | None) -> str:
        if media_type == "series" and season is not None and episode is not None:
            return f"{imdb_id}:{season}:{episode}"
        return imdb_id

    def search(self, imdb_id, media_type, season=None, episode=None) -> list[Stream]:
        stream_id = self._stream_id(imdb_id, media_type, season, episode)
        url = f"{self.host}/{self._config_segment()}/stream/{media_type}/{stream_id}.json"
        data = get_json(url, timeout=60)
        streams = []
        for item in data.get("streams", []):
            play_url = item.get("url")
            if not play_url:
                continue  # skip non-playable rows (e.g. "sync your account" prompts)
            name = (item.get("name") or "").replace("\n", " ")
            description = item.get("description") or item.get("title") or ""
            streams.append(Stream(
                title=_release_title(description) or name,
                url=play_url,
                quality=_quality(f"{name} {description}"),
                cached=("⚡" in name) or ("TB" in name),  # ⚡ marker
                size=_size(description),
                seeders=_seeders(description),
                raw_name=name,
                raw_description=description.replace("\n", " "),
            ))
        return streams
