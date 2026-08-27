from resources.lib import release_groups as rg


def test_category():
    assert rg.category("Movie.2024.2160p.REMUX.mkv") == "remux"
    assert rg.category("Show.S01E01.1080p.WEB-DL.x264") == "web"
    assert rg.category("Movie.2024.1080p.BluRay.x264") == "hd_bluray"
    assert rg.category("Movie.2024.2160p.BluRay.x265") == "uhd_bluray"
    assert rg.category("Movie.2024.DVDRip.XviD") is None


def test_extract_group():
    assert rg.extract_group("Movie.2024.2160p.REMUX-FraMeSToR") == "FraMeSToR"
    assert rg.extract_group("Movie.2024.1080p.BluRay-NTb [TGx]") == "NTb"
    assert rg.extract_group("Movie.2024.1080p.WEB-DL-FLUX.mkv") == "FLUX"
    assert rg.extract_group("Movie.2024.1080p.WEB no dash group") == ""


def test_tier_bonus_and_label():
    # FraMeSToR is a tier-1 remux group
    assert rg.tier_bonus("Movie.2024.2160p.REMUX-FraMeSToR") == rg.TIER_BONUS[1]
    assert rg.tier_label("Movie.2024.2160p.REMUX-FraMeSToR") == "Tier 1"
    # FLUX is a tier-1 web group
    assert rg.tier_bonus("Show.S01E01.1080p.WEB-DL-FLUX") == rg.TIER_BONUS[1]
    # unknown group -> no bonus / no label
    assert rg.tier_bonus("Movie.2024.2160p.REMUX-NobodyKnows") == 0
    assert rg.tier_label("Movie.2024.2160p.REMUX-NobodyKnows") == ""


def test_tiers_are_ordered():
    assert rg.TIER_BONUS[1] > rg.TIER_BONUS[2] > rg.TIER_BONUS[3] > 0
