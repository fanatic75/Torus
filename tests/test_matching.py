from resources.lib import matching as m


def test_normalize_strips_year_and_punct():
    assert m.normalize("Dark.2017") == "dark"
    assert m.normalize("His_Dark-Materials") == "his dark materials"


def test_release_show_title_series():
    assert m.release_show_title("DARK.S01E01.Secrets.2160p.NF-NTb", True) == "dark"
    assert m.release_show_title("His.Dark.Materials.S01E01.2160p-NTb", True) == "his dark materials"
    assert m.release_show_title("Dark.Matter.S01E01.2160p-G66", True) == "dark matter"
    assert m.release_show_title("Show 1x05 whatever", True) == "show"


def test_release_show_title_movie():
    assert m.release_show_title("Dune.2021.2160p.REMUX-FraMeSToR", False) == "dune"


def test_matches_rejects_other_shows_named_dark():
    assert m.matches("DARK.S01E01.Secrets.2160p.NF-NTb", "Dark", True) is True
    assert m.matches("Dark S01E01 2160p-Kitsune", "Dark", True) is True
    assert m.matches("His.Dark.Materials.S01E01.2160p-NTb", "Dark", True) is False
    assert m.matches("Dark.Matter.S01E01.2160p-G66", "Dark", True) is False
    assert m.matches("Star Wars Maul S01E01 The Dark Revenge 2160p-FLUX", "Dark", True) is False


def test_matches_empty_expected_is_false():
    assert m.matches("Dark.S01E01", "", True) is False


def test_matches_tolerates_separator_in_marker():
    assert m.matches("Dark S01 E01 - Hardcoded Eng Subs", "Dark", True) is True
    assert m.matches("Dark.S01.E01.1080p", "Dark", True) is True
