"""Source ranking — deterministic, home-theater-biased scoring.

Priority order, enforced by weight separation so higher factors never lose to
lower ones:
    resolution  >>  source (REMUX>BluRay>WEB-DL)  >>  release-group tier (TRaSH)
    >>  HDR/Dolby Vision  >>  lossless audio
Junk (CAM/TS) is pushed to the bottom. M4 will layer configurable profiles on top.
"""

from __future__ import annotations
import re

from . import matching, release_groups
from .providers.base import Stream

_DV = re.compile(r"(?<![a-z])dv(?![a-z])")
# "Open Matte" releases expose the full (un-cropped) frame; matches OpenMatte,
# open.matte, open-matte, open_matte, "open matte".
_OPEN_MATTE = re.compile(r"open[\s._-]*matte", re.IGNORECASE)


def score(stream: Stream) -> int:
    text = f"{stream.raw_name} {stream.raw_description} {stream.title}".lower()
    points = 0

    # resolution — dominant
    if any(k in text for k in ("2160", "4k", "uhd")):
        points += 100000
    elif "1080" in text:
        points += 50000
    elif "720" in text:
        points += 20000
    elif "480" in text:
        points += 8000

    # source
    if "remux" in text:
        points += 6000
    elif "bluray" in text or "blu-ray" in text:
        points += 4000
    elif any(k in text for k in ("web-dl", "webdl", "web dl")):
        points += 2000
    elif "webrip" in text:
        points += 1000

    # release-group tier (TRaSH Guides) — tiebreaker within a quality bracket
    points += release_groups.tier_bonus(stream.title or stream.raw_name)

    # HDR / Dolby Vision
    if "dolby vision" in text or "dovi" in text or _DV.search(text):
        points += 600
    if "hdr10+" in text or "hdr10plus" in text:
        points += 300
    elif "hdr" in text:
        points += 200

    # audio
    if "truehd" in text or "atmos" in text:
        points += 200
    elif any(k in text for k in ("dts-hd", "dtshd", "dts:x", "dtsx")):
        points += 150

    if stream.cached:
        points += 50

    # junk
    if any(bad in text for bad in ("camrip", "hdcam", "telesync", " cam ", " ts ")):
        points -= 100000

    return points


def rank(streams: list[Stream], expected: str = "", series: bool = False) -> list[Stream]:
    """Rank best-first. When `expected` (the show/movie title) is given, whether a
    release actually belongs to that title is the DOMINANT factor — a correct-show
    source always outranks a wrong-show one regardless of quality — so one-click
    Play and next-episode auto-pick can't grab a mismatched release. Fail-open: if
    nothing matches, ordering falls back to pure quality score.
    """
    if not expected:
        return sorted(streams, key=score, reverse=True)
    return sorted(
        streams,
        key=lambda s: (matching.matches(s.title or s.raw_name, expected, series), score(s)),
        reverse=True,
    )


def is_open_matte(stream: Stream) -> bool:
    """True when a release advertises an Open Matte (un-cropped, full-frame) cut."""
    text = " ".join(t for t in (stream.title, stream.raw_name, stream.raw_description) if t)
    return bool(_OPEN_MATTE.search(text))


def open_matte_first(streams: list[Stream]) -> list[Stream]:
    """Stable partition of an already-ranked list: Open Matte releases float to the
    top, everything else keeps its existing order. Used by the movie Choose-source
    screen so the un-cropped cut is offered first without disturbing the rest."""
    open_matte = [s for s in streams if is_open_matte(s)]
    rest = [s for s in streams if not is_open_matte(s)]
    return open_matte + rest
