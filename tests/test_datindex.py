import os
from pathlib import Path

from romledger import datindex, state

SHA = "A" * 40
DAT = f"""clrmamepro (
\tname "Test"
\tversion "2026.10.01"
)

game (
\tname "Alpha (USA)"
\tdescription "Alpha (USA)"
\trom ( name "Alpha (USA).nes" size 1024 crc 0000ABCD md5 {"B" * 32} sha1 {SHA} )
)

game (
\tname "Beta (Europe) (En,Fr)"
\trom ( name "weird \\"quoted\\" size 9 (x).nes" size 12 crc 11111111 )
\trom ( name "b2.nes" size ? sha1 {"c" * 40} )
)

game (
\tname "Bare (Japan)"
)

game (
\tdescription "No name"
\trom ( name "n.nes" size 1 )
)
"""


def test_parse_reads_hashes_sizes_and_games() -> None:
    roms = list(datindex.parse(DAT.splitlines()))
    assert roms == [
        datindex.Rom(SHA.lower(), "b" * 32, "0000abcd", 1024, "Alpha (USA)"),
        datindex.Rom(None, None, "11111111", 12, "Beta (Europe) (En,Fr)"),
        datindex.Rom("c" * 40, None, None, None, "Beta (Europe) (En,Fr)"),
        datindex.Rom(None, None, None, None, "Bare (Japan)"),
    ]


def test_parse_ignores_name_lines_after_the_first() -> None:
    lines = ["game (", '\tname "One"', '\tname "Two"', ")"]
    assert [rom.game for rom in datindex.parse(lines)] == ["One"]


def test_games_are_unique_with_normalized_title_and_region() -> None:
    games = datindex.games_of(datindex.parse(DAT.splitlines()))
    assert games == [
        state.IndexedGame("Alpha (USA)", "alpha", "usa"),
        state.IndexedGame("Beta (Europe) (En,Fr)", "beta", "europe"),
        state.IndexedGame("Bare (Japan)", "bare", "japan"),
    ]


def test_ensure_rebuilds_only_when_the_version_changes(tmp_path: Path) -> None:
    dat = tmp_path / "t.dat"
    dat.write_text(DAT)
    with state.State(tmp_path / "state.db") as database:
        assert database.index_stamp("nes") is None
        assert datindex.ensure(database, "nes", dat) is True
        stamp = database.index_stamp("nes")
        assert stamp is not None
        assert stamp.version == "2026.10.01"
        assert datindex.ensure(database, "nes", dat) is False
        dat.write_text(DAT.replace("2026.10.01", "2026.11.01").replace("Bare (Japan)", "New (USA)"))
        assert datindex.ensure(database, "nes", dat) is True
        assert [item.game for item in database.locate_title("nes", "new")] == ["New (USA)"]
        assert database.locate_title("nes", "bare") == []


def test_ensure_reindexes_a_changed_dat_without_a_version(tmp_path: Path) -> None:
    dat = tmp_path / "t.dat"
    dat.write_text(DAT.replace('\tversion "2026.10.01"\n', ""))
    with state.State(tmp_path / "state.db") as database:
        assert datindex.ensure(database, "nes", dat) is True
        assert datindex.ensure(database, "nes", dat) is False
        dat.write_text(dat.read_text().replace("Bare (Japan)", "New (USA)"))
        assert datindex.ensure(database, "nes", dat) is True
        assert [item.game for item in database.locate_title("nes", "new")] == ["New (USA)"]


def test_ensure_reindexes_when_only_the_mtime_changes(tmp_path: Path) -> None:
    dat = tmp_path / "t.dat"
    dat.write_text(DAT)
    with state.State(tmp_path / "state.db") as database:
        assert datindex.ensure(database, "nes", dat) is True
        stat = dat.stat()
        os.utime(dat, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        assert datindex.ensure(database, "nes", dat) is True
