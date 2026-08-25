"""Release-group quality tiers, curated from TRaSH Guides (https://trash-guides.info).

A snapshot of TRaSH Guides' Radarr release-group tier custom formats. We parse a
torrent's release group and, matched against the tier for its source category,
add a small ranking bonus so reputable scene/p2p groups float to the top of a
given quality bracket — without ever overriding resolution or source.

Credit: the group tier lists are maintained by the TRaSH Guides community.
"""
import re

# category -> tier -> [group names], verbatim from TRaSH Guides (English general).
_TIERS = {
    "remux": {
        1: ["3L", "ATELiER", "BLURANiUM", "BMF", "BiZKiT", "CiNEPHiLES",
            "FraMeSToR", "PiRAMiDHEAD", "PmP", "WiLDCAT", "ZQ"],
        2: ["NCmt", "SURFINBIRD", "SiCFoI", "TEPES", "playBD"],
        3: ["12GaugeShotgun", "EPSiLON", "HiFi", "KRaLiMaRKo", "NTb", "PTP",
            "SumVision", "TOA", "TRiToN", "decibeL", "iFT"],
    },
    "uhd_bluray": {
        1: ["CtrlHD", "DON", "MainFrame", "W4NK3R"],
        2: ["HQMUX", "HiDt", "RandomBytes"],
        3: ["BHDStudio", "HONE", "PTer", "SPHD", "WEBDV", "hallowed"],
    },
    "hd_bluray": {
        1: ["ATELiER", "BBQ", "BMF", "CRiSC", "Chotab", "CtrlHD", "DON",
            "Dariush", "EDPH", "EbP", "Geek", "LolHD", "NCmt", "PTer", "TDD",
            "TayTO", "TnP", "VietHD", "Z0N3", "ZQ", "ZoroSenpai", "c0kE", "decibeL"],
        2: ["EA", "HiDt", "HiSD", "NTb", "QOQ", "SA89", "iFT", "sbR"],
        3: ["BHDStudio", "HONE", "HiFi", "LoRD", "SPHD", "W4NK3R", "hallowed", "playHD"],
    },
    "web": {
        1: ["ABBIE", "AJP69", "APEX", "BLUTONiUM", "BYNDR", "CMRG", "CRFW",
            "CRUD", "FLUX", "GNOME", "HONE", "KiNGS", "Kitsune", "MADSKY",
            "NOSiViD", "NTG", "NTb", "PAXA", "PEXA", "RAWR", "SiC", "TEPES",
            "TheFarm", "XEPA", "ZoroSenpai"],
        2: ["4KBEC", "CEBEX", "Flights", "MZABI", "MiU", "PHOENiX", "SMURF",
            "SbR", "TOMMY", "XEBEC", "dB", "monkee", "playWEB"],
        3: ["BLOOM", "Dooky", "GNOMiSSiON", "HHWEB", "NINJACENTRAL", "NPMS",
            "ROCCaT", "SLiGNOME", "SiGMA", "SwAgLaNdEr"],
    },
}

TIER_BONUS = {1: 1200, 2: 1000, 3: 800}

_LOOKUP = {
    cat: {group.lower(): tier for tier, groups in tiers.items() for group in groups}
    for cat, tiers in _TIERS.items()
}


def category(text: str) -> str | None:
    low = text.lower()
    if "remux" in low:
        return "remux"
    if any(k in low for k in ("web-dl", "webdl", "web dl", "webrip", ".web.", "-web-", " web ")):
        return "web"
    if any(k in low for k in ("bluray", "blu-ray", "brrip", "bdrip", "bd25", "bd50")):
        return "uhd_bluray" if any(k in low for k in ("2160", "4k", "uhd")) else "hd_bluray"
    return None


def extract_group(title: str) -> str:
    """The release group is the token after the final '-' (scene/p2p convention)."""
    text = re.sub(r"\[[^\]]*\]\s*$", "", title.strip())          # strip trailing [TGx]
    text = re.sub(r"\.(mkv|mp4|avi|ts|m2ts|iso)$", "", text, flags=re.IGNORECASE)
    match = re.search(r"-([A-Za-z0-9]{2,25})$", text)
    return match.group(1) if match else ""


def _best_tier(title: str) -> int | None:
    group = extract_group(title).lower()
    if not group:
        return None
    cat = category(title)
    categories = [cat] if cat else list(_LOOKUP)
    best = None
    for candidate in categories:
        tier = _LOOKUP[candidate].get(group)
        if tier and (best is None or tier < best):
            best = tier
    return best


def tier_bonus(title: str) -> int:
    tier = _best_tier(title)
    return TIER_BONUS[tier] if tier else 0


def tier_label(title: str) -> str:
    tier = _best_tier(title)
    return f"Tier {tier}" if tier else ""
