"""Source ranking — deterministic, home-theater-biased scoring.

Priority order, enforced by weight separation so higher factors never lose to
lower ones:
    resolution  >>  source (REMUX>BluRay>WEB-DL)  >>  release-group tier (TRaSH)
    >>  HDR/Dolby Vision  >>  lossless audio
Junk (CAM/TS) is pushed to the bottom. M4 will layer configurable profiles on top.
"""

from __future__ import annotations
import re

from . import release_groups
from .providers.base import Stream

_DV = re.compile(r"(?<![a-z])dv(?![a-z])")


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


def rank(streams: list[Stream]) -> list[Stream]:
    return sorted(streams, key=score, reverse=True)
