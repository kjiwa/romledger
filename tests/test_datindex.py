import os
from pathlib import Path
from xml.etree import ElementTree

from romledger import catalog, datindex, dats, state

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
        state.DatRom(SHA.lower(), "b" * 32, "0000abcd", 1024, "Alpha (USA)", "Alpha (USA).nes", 0),
        state.DatRom(
            None, None, "11111111", 12, "Beta (Europe) (En,Fr)", 'weird "quoted" size 9 (x).nes', 1
        ),
        state.DatRom("c" * 40, None, None, None, "Beta (Europe) (En,Fr)", "b2.nes", 1),
        state.DatRom(None, None, None, None, "Bare (Japan)", None, 2),
    ]


def test_parse_gives_same_named_games_separate_blocks() -> None:
    lines = [
        *("game (", '\tname "A (USA)"', '\trom ( name "A (USA).a26" size 1 crc 00000001 )', ")"),
        *(
            "game (",
            '\tname "A (USA)"',
            '\trom ( name "A (USA) (Alt).a26" size 1 crc 00000002 )',
            ")",
        ),
    ]
    assert [(rom.name, rom.block) for rom in datindex.parse(lines)] == [
        ("A (USA).a26", 0),
        ("A (USA) (Alt).a26", 1),
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


def test_ensure_stores_rom_names_for_the_catalog(tmp_path: Path) -> None:
    dat = tmp_path / "t.dat"
    dat.write_text(DAT)
    with state.State(tmp_path / "state.db") as database:
        datindex.ensure(database, "nes", dat)
        games = datindex.catalog_games(database.dat_roms("nes"))
    assert games == [
        catalog.Game("Alpha (USA)", ("Alpha (USA).nes",)),
        catalog.Game("Bare (Japan)", ()),
        catalog.Game("Beta (Europe) (En,Fr)", ('weird "quoted" size 9 (x).nes', "b2.nes")),
    ]


def test_write_subset_keeps_the_header_name_and_chosen_games(tmp_path: Path) -> None:
    roms = [
        state.DatRom(SHA, "b" * 32, "0000abcd", 1024, "Alpha & <Co> (USA)", 'A "1".nes'),
        state.DatRom(None, None, None, None, "Bare (USA)", None),
    ]
    path = tmp_path / "subset.dat"
    datindex.write_subset(path, "Nintendo - NES", roms)
    root = ElementTree.parse(path).getroot()  # noqa: S314
    assert root.findtext("header/name") == "Nintendo - NES"
    games = {game.get("name"): game.findall("rom") for game in root.findall("game")}
    assert list(games) == ["Alpha & <Co> (USA)", "Bare (USA)"]
    assert [rom.attrib for rom in games["Alpha & <Co> (USA)"]] == [
        {"name": 'A "1".nes', "size": "1024", "crc": "0000abcd", "md5": "b" * 32, "sha1": SHA}
    ]
    assert games["Bare (USA)"] == []


def test_write_subset_keeps_same_named_blocks_as_separate_games(tmp_path: Path) -> None:
    roms = [
        state.DatRom(None, None, "00000001", 1, "A (USA)", "A (USA).a26", 0),
        state.DatRom(None, None, "00000002", 1, "A (USA)", "A (USA) (Alt).a26", 1),
    ]
    path = tmp_path / "subset.dat"
    datindex.write_subset(path, "Atari - 2600", roms)
    root = ElementTree.parse(path).getroot()  # noqa: S314
    assert [[rom.get("name") for rom in game.findall("rom")] for game in root.findall("game")] == [
        ["A (USA).a26"],
        ["A (USA) (Alt).a26"],
    ]


def test_subset_header_name_round_trips_with_an_ampersand(tmp_path: Path) -> None:
    dat = tmp_path / "t.dat"
    dat.write_text(DAT.replace('name "Test"', 'name "Nintendo & Co - NES"'))
    path = tmp_path / "subset.dat"
    datindex.write_subset(path, dats.name_of(dat), [])
    assert ElementTree.parse(path).getroot().findtext("header/name") == dats.name_of(dat)  # noqa: S314
    assert dats.name_of(dat) == "Nintendo & Co - NES"
