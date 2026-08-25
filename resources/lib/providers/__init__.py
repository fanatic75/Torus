"""Provider factory + a parallel merging provider.

The default queries Comet and Torrentio concurrently and merges their results,
deduped by release filename. This both widens coverage and is resilient: if one
host is slow or down, the other's results still come through.
"""

from __future__ import annotations
import concurrent.futures
import re

from .. import config
from ..http import log
from .base import Provider, Stream
from .comet import CometProvider
from .torrentio import TorrentioProvider


def _dedup_key(stream: Stream) -> str:
    return re.sub(r"[^a-z0-9]", "", stream.title.lower()) or stream.url


class MergedProvider(Provider):
    """Query several providers concurrently; merge + dedup; tolerate failures."""

    def __init__(self, providers: list[Provider]):
        self.providers = providers

    def search(self, imdb_id, media_type, season=None, episode=None) -> list[Stream]:
        results: dict[Provider, list[Stream]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.providers)) as pool:
            futures = {
                provider: pool.submit(provider.search, imdb_id, media_type, season, episode)
                for provider in self.providers
            }
            for provider, future in futures.items():
                try:
                    results[provider] = future.result()
                except Exception as exc:  # noqa: BLE001 - one provider down != failure
                    log(f"provider {provider.__class__.__name__} failed: {exc}")
                    results[provider] = []

        merged, seen = [], set()
        for provider in self.providers:  # stable order (Comet first)
            for stream in results.get(provider, []):
                key = _dedup_key(stream)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(stream)
        return merged


def get_provider() -> Provider:
    key = config.torbox_token()
    name = config.provider()
    if name == "comet":
        return CometProvider(key)
    if name == "torrentio":
        return TorrentioProvider(key)
    # default: merge both for coverage + resilience
    return MergedProvider([CometProvider(key), TorrentioProvider(key)])
