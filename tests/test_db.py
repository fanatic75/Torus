"""SQLite layer: watchlist, custom folders, resume/Continue Watching."""
from resources.lib import db


# --- watchlist -------------------------------------------------------------
def test_watchlist_add_remove(tmp_profile):
    db.add_watchlist("tt1", "movie", "Movie One", "p1")
    assert db.in_watchlist("tt1")
    assert db.watchlist_ids() == {"tt1"}
    assert [r["imdb"] for r in db.list_watchlist()] == ["tt1"]
    db.remove_watchlist("tt1")
    assert not db.in_watchlist("tt1")
    assert db.list_watchlist() == []


# --- folders ---------------------------------------------------------------
def test_create_folder_dedup_and_blank(tmp_profile):
    fid = db.create_folder("Harry Potter")
    assert isinstance(fid, int)
    assert db.create_folder("harry potter") == fid   # case-insensitive dedup
    assert db.create_folder("   ") is None            # blank rejected
    assert db.create_folder("") is None


def test_root_vs_folder_listing_and_counts(tmp_profile):
    fid = db.create_folder("Harry Potter")
    db.add_watchlist("tt2", "movie", "HP1", "", folder_id=fid)
    db.add_watchlist("tt3", "movie", "Loose", "", None)
    assert [r["imdb"] for r in db.list_watchlist()] == ["tt3"]      # root only
    assert [r["imdb"] for r in db.list_watchlist(fid)] == ["tt2"]   # folder only
    folders = db.list_folders()
    assert folders[0]["name"] == "Harry Potter"
    assert folders[0]["count"] == 1


def test_move_between_folders_and_root(tmp_profile):
    fid = db.create_folder("HP")
    db.add_watchlist("tt3", "movie", "Loose", "", None)
    db.move_to_folder("tt3", fid)
    assert {r["imdb"] for r in db.list_watchlist(fid)} == {"tt3"}
    assert db.list_watchlist() == []
    db.move_to_folder("tt3", None)                    # back to root
    assert [r["imdb"] for r in db.list_watchlist()] == ["tt3"]


def test_rename_folder_trim_and_collision(tmp_profile):
    a = db.create_folder("A")
    b = db.create_folder("B")
    assert db.rename_folder(a, "  Wizards ") is True
    assert db.get_folder(a)["name"] == "Wizards"
    assert db.rename_folder(b, "wizards") is False    # name taken (case-insensitive)
    assert db.rename_folder(a, "wizards") is True      # own name, case change, allowed


def test_delete_folder_cascades(tmp_profile):
    fid = db.create_folder("X")
    db.add_watchlist("tt9", "movie", "x", "", folder_id=fid)
    db.add_watchlist("tt10", "movie", "root", "", None)
    db.delete_folder(fid)
    assert db.get_folder(fid) is None
    assert not db.in_watchlist("tt9")   # its titles removed with it
    assert db.in_watchlist("tt10")      # others untouched


# --- pinning + manual order ------------------------------------------------
def test_new_titles_appear_newest_first(tmp_profile):
    db.add_watchlist("tt1", "movie", "First", "", None)
    db.add_watchlist("tt2", "movie", "Second", "", None)
    db.add_watchlist("tt3", "movie", "Third", "", None)
    assert [r["imdb"] for r in db.list_watchlist()] == ["tt3", "tt2", "tt1"]


def test_pin_floats_to_top(tmp_profile):
    for i in range(1, 4):
        db.add_watchlist(f"tt{i}", "movie", f"M{i}", "", None)
    # order is tt3, tt2, tt1; pin the bottom one
    db.set_pinned("tt1", True)
    assert db.is_pinned("tt1")
    assert [r["imdb"] for r in db.list_watchlist()][0] == "tt1"
    assert db.list_watchlist()[0]["pinned"] == 1
    db.set_pinned("tt1", False)
    assert [r["imdb"] for r in db.list_watchlist()] == ["tt3", "tt2", "tt1"]


def test_set_watchlist_order_persists(tmp_profile):
    for i in range(1, 4):
        db.add_watchlist(f"tt{i}", "movie", f"M{i}", "", None)
    db.set_watchlist_order(["tt1", "tt3", "tt2"])
    assert [r["imdb"] for r in db.list_watchlist()] == ["tt1", "tt3", "tt2"]


def test_pinned_beats_manual_order(tmp_profile):
    for i in range(1, 4):
        db.add_watchlist(f"tt{i}", "movie", f"M{i}", "", None)
    db.set_watchlist_order(["tt1", "tt2", "tt3"])
    db.set_pinned("tt3", True)                       # pinned floats above order
    assert [r["imdb"] for r in db.list_watchlist()] == ["tt3", "tt1", "tt2"]


def test_set_folder_order_persists(tmp_profile):
    a = db.create_folder("A")
    b = db.create_folder("B")
    c = db.create_folder("C")
    db.set_folder_order([c, a, b])
    assert [f["id"] for f in db.list_folders()] == [c, a, b]


# --- resume / Continue Watching -------------------------------------------
def test_progress_save_get_clear(tmp_profile):
    db.save_progress("tt1", "movie", 0, 0, 300, 1000, "M", "p", "url")
    p = db.get_progress("tt1")
    assert p["position"] == 300 and p["url"] == "url"
    db.clear_progress("tt1")
    assert db.get_progress("tt1") is None


def test_continue_hides_finished_and_shows_inprogress(tmp_profile):
    db.save_progress("tt1", "movie", 0, 0, 300, 1000, "M1", "p", "u1")   # 30% -> shown
    db.save_progress("tt2", "movie", 0, 0, 990, 1000, "M2", "p", "u2")   # 99% -> hidden
    cont = {r["imdb"] for r in db.list_continue()}
    assert "tt1" in cont and "tt2" not in cont


def test_next_up_appears_in_continue(tmp_profile):
    db.set_next_up("tt5", "series", 1, 2, "Show", "p")
    rows = db.list_continue()
    assert any(r["imdb"] == "tt5" and r["nextup"] == 1 for r in rows)
