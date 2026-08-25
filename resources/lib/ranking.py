"""Source ranking — deterministic quality scoring.

A light home-theater-biased scorer for M2: resolution, source (REMUX > BluRay >
WEB-DL), HDR/Dolby Vision, lossless audio, with junk (CAM/TS) pushed to the
bottom. M4 will expand this into configurable quality profiles.
"""
from .providers.base import Stream


def score(stream: Stream) -> int:
    text = f"{stream.raw_name} {stream.raw_description} {stream.title}".lower()
    points = 0

    # resolution
    if "2160" in text or "4k" in text or "uhd" in text:
        points += 4000
    elif "1080" in text:
        points += 2000
    elif "720" in text:
        points += 1000

    # source
    if "remux" in text:
        points += 2000
    elif "bluray" in text or "blu-ray" in text:
        points += 1200
    elif "web-dl" in text or "webdl" in text or "web dl" in text:
        points += 800
    elif "webrip" in text:
        points += 500

    # HDR / Dolby Vision
    if "dv" in text or "dolby vision" in text or "dovi" in text:
        points += 900
    if "hdr10+" in text or "hdr10plus" in text:
        points += 500
    elif "hdr" in text:
        points += 400

    # audio
    if "truehd" in text or "atmos" in text:
        points += 400
    elif "dts-hd" in text or "dtshd" in text or "dts:x" in text or "dtsx" in text:
        points += 300

    # cached bonus (should be all-cached, but keep the bias explicit)
    if stream.cached:
        points += 100

    # junk
    if any(bad in text for bad in ("cam", "ts ", "telesync", "hdcam", "camrip")):
        points -= 6000

    return points


def rank(streams: list[Stream]) -> list[Stream]:
    return sorted(streams, key=score, reverse=True)
