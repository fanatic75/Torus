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


# --- match-aware ranking (Dark bug) ---------------------------------------
def test_match_beats_quality():
    # a correct-show 720p must outrank a wrong-show 2160p
    correct = Stream(title="DARK.S01E01.720p-NTb", url="c", raw_name="DARK.S01E01.720p-NTb")
    wrong = Stream(title="Dark.Matter.S01E01.2160p-G66", url="w", raw_name="Dark.Matter.S01E01.2160p-G66")
    ranked = rank([wrong, correct], expected="Dark", series=True)
    assert ranked[0].url == "c"


def test_match_keeps_all_sources():
    streams = [Stream(title="His.Dark.Materials.S01E01.2160p", url="a", raw_name="His.Dark.Materials.S01E01.2160p"),
               Stream(title="DARK.S01E01.1080p-NTb", url="b", raw_name="DARK.S01E01.1080p-NTb")]
    ranked = rank(streams, expected="Dark", series=True)
    assert {s.url for s in ranked} == {"a", "b"}   # nothing dropped
    assert ranked[0].url == "b"                     # correct show on top


def test_no_expected_is_quality_only():
    a = Stream(title="X 2160p", url="a", raw_name="X 2160p")
    b = Stream(title="X 1080p", url="b", raw_name="X 1080p")
    assert rank([b, a])[0].url == "a"   # unchanged legacy behaviour
