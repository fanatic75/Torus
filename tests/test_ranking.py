from resources.lib.ranking import rank, score
from resources.lib.providers.base import Stream


def s(title):
    return Stream(title=title, url="u", raw_name=title, raw_description="")


def test_resolution_dominates():
    assert score(s("Movie 2160p")) > score(s("Movie 1080p")) > score(s("Movie 720p"))


def test_source_order_within_resolution():
    assert (score(s("Movie 1080p REMUX"))
            > score(s("Movie 1080p BluRay"))
            > score(s("Movie 1080p WEB-DL")))


def test_cam_is_demoted_below_zero():
    assert score(s("Movie 1080p CAMRip")) < 0


def test_group_tier_breaks_ties():
    assert score(s("Movie 2160p REMUX-FraMeSToR")) > score(s("Movie 2160p REMUX-NobodyGroup"))


def test_resolution_beats_everything_lower():
    # a bare 2160p should still outrank a fully-loaded 1080p
    assert score(s("Movie 2160p")) > score(s("Movie 1080p REMUX HDR TrueHD-FraMeSToR"))


def test_rank_orders_best_first():
    streams = [s("Movie 720p WEB-DL"),
               s("Movie 2160p REMUX-FraMeSToR"),
               s("Movie 1080p BluRay")]
    ranked = rank(streams)
    assert ranked[0].title.startswith("Movie 2160p")
    assert ranked[-1].title.startswith("Movie 720p")
