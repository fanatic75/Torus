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
    # Infohash is the cryptographic torrent id — the reliable "same release"
    # signal across providers. Fall back to a normalized title, then the url.
    return stream.infohash or re.sub(r"[^a-z0-9]", "", stream.title.lower()) or stream.url


# A source search must never hang on one slow/dead provider (e.g. elfhosted/Comet
# stalling): return as soon as the FASTEST provider answers, then allow only a
# short grace for the rest. The whole search is hard-capped either way.
SEARCH_TIMEOUT = 12    # give up entirely if not even one provider has answered
STRAGGLER_GRACE = 3    # after the first answers, wait at most this long for others


class MergedProvider(Provider):
    """Query several providers concurrently; merge + dedup; tolerate failures.

    Crucially, a stalled provider can't hold up the ones that already answered:
    we wait for the first to return, give the rest a brief grace, then move on
    with whatever we have. That's the whole point of running several providers —
    if one is down, the others still work, with no user-visible delay."""

    def __init__(self, providers: list[Provider],
                 search_timeout: float = SEARCH_TIMEOUT,
                 straggler_grace: float = STRAGGLER_GRACE):
        self.providers = providers
        self.search_timeout = search_timeout
        self.straggler_grace = straggler_grace

    def search(self, imdb_id, media_type, season=None, episode=None) -> list[Stream]:
        results: dict[Provider, list[Stream]] = {}
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(self.providers))
        try:
            futures = {
                pool.submit(provider.search, imdb_id, media_type, season, episode): provider
                for provider in self.providers
            }
            # Wait for the first provider to answer, then only a short grace for
            # the rest — a dead provider is simply left behind, not waited on.
            done, pending = concurrent.futures.wait(
                futures, timeout=self.search_timeout,
                return_when=concurrent.futures.FIRST_COMPLETED)
            if pending:
                extra, _ = concurrent.futures.wait(pending, timeout=self.straggler_grace)
                done |= extra
            for future, provider in futures.items():
                name = provider.__class__.__name__
                if future not in done:
                    log(f"provider {name} too slow — skipped so it can't block the others")
                    results[provider] = []
                    continue
                try:
                    results[provider] = future.result()
                except Exception as exc:  # noqa: BLE001 - one provider down != failure
                    log(f"provider {name} failed: {exc}")
                    results[provider] = []
        finally:
            # Don't block on a still-running (stalled) provider request; let its
            # thread finish in the background — we already have our results.
            pool.shutdown(wait=False)

        merged, seen = [], set()
        for provider in self.providers:  # stable order (Torrentio first)
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
    # Default: merge both for coverage + resilience. Torrentio FIRST so that when
    # the same torrent (matched by infohash) comes from both, we keep Torrentio's
    # URL — it redirects straight to the TorBox CDN, whereas Comet proxies the
    # bytes through elfhosted, which is frequently slow/timing out.
    return MergedProvider([TorrentioProvider(key), CometProvider(key)])
