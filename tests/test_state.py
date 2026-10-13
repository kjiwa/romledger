from pathlib import Path

import pytest

from romledger.state import Counts, Item, State

ITEMS = [
    Item("Beta (USA)", "missing", None),
    Item("Alpha (USA)", "have", "/a"),
    Item("Zed (USA)", "missing", None),
    Item("Cat (USA)", "inbox", "/c"),
]


def fill(database: State, items: list[Item] = ITEMS) -> None:
    database.replace_platform("nes", items, ["/u1", "/u2"], "2026.10.01", "t1")


def test_counts_only_scanned(tmp_path: Path) -> None:
    with State(tmp_path / "state.db") as database:
        assert database.counts() == {}
        fill(database)
        assert database.counts() == {"nes": Counts(have=1, inbox=1, missing=2, unmatched=2)}


def test_scanned_with_no_entries_still_counts(tmp_path: Path) -> None:
    with State(tmp_path / "state.db") as database:
        database.replace_platform("nes", [], [], "v", "t")
        assert database.counts() == {"nes": Counts(0, 0, 0, 0)}


def test_missing_sorted_and_scanned_at(tmp_path: Path) -> None:
    with State(tmp_path / "state.db") as database:
        assert database.scanned_at("nes") is None
        fill(database)
        assert database.missing("nes") == ["Beta (USA)", "Zed (USA)"]
        assert database.scanned_at("nes") == "t1"


def test_replace_overwrites_platform_only(tmp_path: Path) -> None:
    with State(tmp_path / "state.db") as database:
        fill(database)
        database.replace_platform("snes", [Item("X", "missing", None)], [], "v", "t")
        database.replace_platform("nes", [Item("Alpha (USA)", "have", "/a")], [], "v2", "t2")
        counts = database.counts()
    assert counts["nes"] == Counts(1, 0, 0, 0)
    assert counts["snes"] == Counts(0, 0, 1, 0)


def test_replace_is_transactional(tmp_path: Path) -> None:
    with State(tmp_path / "state.db") as database:
        fill(database)
        with pytest.raises(Exception, match="CHECK"):
            database.replace_platform("nes", [Item("Q", "bogus", None)], [], "v", "t")
        assert database.counts()["nes"] == Counts(1, 1, 2, 2)
        assert database.scanned_at("nes") == "t1"


def test_reopen_persists(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "state.db"
    with State(path) as database:
        fill(database)
    with State(path) as database:
        assert database.missing("nes") == ["Beta (USA)", "Zed (USA)"]
