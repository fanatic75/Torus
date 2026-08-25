"""Torrentio provider — Stremio-protocol source discovery via a Torrentio instance.

Config is a pipe-delimited segment (unlike Comet's base64). We ask for cached
TorBox results only (`debridoptions=nodownloadlinks` + filtering on the `[TB+]`
marker). The stream `url` is a Torrentio resolve link that redirects to the
TorBox stream.
"""

from __future__ import annotations
import re

from ..http import get_json
from .base import Provider, Stream

DEFAULT_HOST = "https://torrentio.strem.fun"

_SIZE = re.compile(r"([\d.]+\s*[GMK]B)", re.IGNORECASE)
_SEEDERS = re.compile(r"\U0001F464\s*(\d+)")  # 👤 N
_RES = [("2160p", ("2160", "4k", "uhd")), ("1080p", ("1080",)),
        ("720p", ("720",)), ("480p", ("480",))]


def _quality(text: str) -> str:
    low = text.lower()
    for label, needles in _RES:
        if any(n in low for n in needles):
            return label
    return ""


class TorrentioProvider(Provider):
    def __init__(self, torbox_key: str, host: str = DEFAULT_HOST):
        self.key = torbox_key
        self.host = host.rstrip("/")

    def _config_segment(self) -> str:
        return f"debridoptions=nodownloadlinks|torbox={self.key}"

    @staticmethod
    def _stream_id(imdb_id, media_type, season, episode) -> str:
        if media_type == "series" and season is not None and episode is not None:
            return f"{imdb_id}:{season}:{episode}"
        return imdb_id

    def search(self, imdb_id, media_type, season=None, episode=None) -> list[Stream]:
        stream_id = self._stream_id(imdb_id, media_type, season, episode)
        url = f"{self.host}/{self._config_segment()}/stream/{media_type}/{stream_id}.json"
        data = get_json(url, timeout=45)
        streams = []
        for item in data.get("streams", []):
            play_url = item.get("url")
            if not play_url:
                continue
            name = (item.get("name") or "").replace("\n", " ")
            if "[tb+]" not in name.lower() and "⚡" not in name:
                continue  # cached-only
            meta = (item.get("title") or "").replace("\n", " ")
            filename = (item.get("behaviorHints") or {}).get("filename") \
                or meta.split("👤")[0].strip()
            size = _SIZE.search(meta)
            seeders = _SEEDERS.search(meta)
            streams.append(Stream(
                title=filename,
                url=play_url,
                quality=_quality(f"{name} {filename}"),
                cached=True,
                size=size.group(1) if size else "",
                seeders=int(seeders.group(1)) if seeders else None,
                raw_name=name,
                raw_description=meta,
            ))
        return streams
