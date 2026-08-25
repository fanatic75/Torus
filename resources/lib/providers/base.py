"""Provider interface — the one abstraction that keeps sources swappable.

A Provider turns a title (IMDb id, optionally season/episode) into a list of
playable Stream objects. Today: Comet. Later: Torrentio, StremThru, self-hosted
instances — all behind this same shape, so the rest of the addon never changes.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Stream:
    title: str                 # release/file name — drives ranking + display
    url: str                   # directly playable URL (resolves to the TorBox stream)
    quality: str = ""          # short label, e.g. "2160p"
    cached: bool = True        # instantly available on TorBox
    size: str = ""             # human-readable size if known, e.g. "78.5 GB"
    seeders: int | None = None
    raw_name: str = ""
    raw_description: str = ""


class Provider:
    def search(self, imdb_id: str, media_type: str,
               season: int | None = None,
               episode: int | None = None) -> list[Stream]:
        """media_type is the Stremio type: 'movie' or 'series'."""
        raise NotImplementedError
