from collections.abc import Sequence
from pathlib import Path

import pytest

from romledger import catalog, config, dats, igir, lookup, registry, scan, state

ReportRow = igir.ReportRow


def row(status: str, game: str = "", path: str = "") -> ReportRow:
    return ReportRow("Nintendo", status, game, path)


def group(*members: str) -> catalog.Group:
    return catalog.Group(members)


def test_library_found_is_have() -> None:
    items, unmatched = scan.classify([group("A")], [row("FOUND", "A", "/l/A")], [])
    assert items == [state.Item("A", "have", "/l/A")]
    assert unmatched == []


def test_inbox_found_not_in_library_is_inbox() -> None:
    items, _ = scan.classify([group("A")], [row("MISSING", "A")], [row("FOUND", "A", "/i/A")])
    assert items == [state.Item("A", "inbox", "/i/A")]


def test_game_in_both_is_have() -> None:
    items, _ = scan.classify([group("A")], [row("FOUND", "A", "/l/A")], [row("FOUND", "A", "/i/A")])
    assert items == [state.Item("A", "have", "/l/A")]


def test_remaining_group_is_missing_under_its_preferred_name() -> None:
    items, _ = scan.classify([group("A (USA)", "A (World)")], [], [row("MISSING", "A (USA)")])
    assert items == [state.Item("A (USA)", "missing", None)]


def test_any_member_found_in_the_library_makes_the_group_have() -> None:
    items, _ = scan.classify(
        [group("A (USA)", "A (USA) (Rev 1)", "A (World)")],
        [row("FOUND", "A (World)", "/l/A")],
        [row("FOUND", "A (USA)", "/i/A")],
    )
    assert items == [state.Item("A (World)", "have", "/l/A")]


def test_any_member_found_in_an_inbox_makes_the_group_inbox() -> None:
    items, _ = scan.classify(
        [group("A (USA)", "A (World)")], [], [row("FOUND", "A (World)", "/i/A")]
    )
    assert items == [state.Item("A (World)", "inbox", "/i/A")]


def test_the_best_found_member_is_recorded() -> None:
    rows = [row("FOUND", "A (World)", "/l/W"), row("FOUND", "A (USA)", "/l/U")]
    items, _ = scan.classify([group("A (USA)", "A (World)")], rows, [])
    assert items == [state.Item("A (USA)", "have", "/l/U")]


def test_found_files_outside_wanted_groups_are_neither_listed_nor_unmatched() -> None:
    items, unmatched = scan.classify([group("A")], [row("FOUND", "Z (Japan)", "/l/Z")], [])
    assert items == [state.Item("A", "missing", None)]
    assert unmatched == []


def test_library_unused_is_unmatched_inbox_unused_ignored() -> None:
    _, unmatched = scan.classify([], [row("UNUSED", path="/l/x")], [row("UNUSED", path="/i/y")])
    assert unmatched == ["/l/x"]


GAMES = ["A (USA)", "B (USA)", "C (USA)", "C (USA) (Unl)", "Z (Japan)"]
DAT = 'clrmamepro (\n\tversion "2026.10.01"\n)\n' + "".join(
    f'game (\n\tname "{name}"\n\trom ( name "{name}.nes" size 1 sha1 {str(i) * 40} )\n)\n'
    for i, name in enumerate(GAMES)
)


def make_config(tmp_path: Path, *, library: bool, include: tuple[str, ...] = ()) -> config.Config:
    roms, inbox = tmp_path / "roms", tmp_path / "inbox"
    inbox.mkdir()
    if library:
        (roms / "nes").mkdir(parents=True)
    return config.Config(
        config.Library(roms, (inbox,)),
        {"nes": config.Platform(registry.load()["nes"].dat, include=include)},
    )


def fake_report(calls: list[tuple[list[Path], Sequence[str]]]) -> scan.IgirReport:
    def report(
        dats: list[Path], inputs: list[Path], cache: Path, excludes: Sequence[str]
    ) -> list[ReportRow]:
        calls.append((list(inputs), excludes))
        assert len(dats) == 1
        if inputs[0].name == "inbox":
            return [row("FOUND", "B (USA)", "/i/B"), row("MISSING", "A (USA)")]
        return [
            row("FOUND", "A (USA)", "/l/A"),
            row("FOUND", "Z (Japan)", "/l/Z"),
            row("UNUSED", path="/l/x"),
        ]

    return report


def write_dat(tmp_path: Path, cfg: config.Config) -> None:
    path = dats.dat_path(tmp_path / "data", cfg.platforms["nes"].dat)
    path.parent.mkdir(parents=True)
    path.write_text(DAT)


def test_scan_platform_with_library(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, library=True)
    write_dat(tmp_path, cfg)
    calls: list[tuple[list[Path], Sequence[str]]] = []
    scan.scan_platform(cfg, "nes", tmp_path / "data", fake_report(calls))
    inbox = tmp_path / "inbox"
    assert calls == [
        ([inbox], igir.inbox_excludes([inbox])),
        ([tmp_path / "roms" / "nes"], ()),
    ]
    with state.State(tmp_path / "data" / "state.db") as database:
        assert database.counts()["nes"] == state.Counts(have=1, inbox=1, missing=1, unmatched=1)
        assert database.missing("nes") == ["C (USA)"]


def test_scan_platform_without_library_dir(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, library=False)
    write_dat(tmp_path, cfg)
    calls: list[tuple[list[Path], Sequence[str]]] = []
    scan.scan_platform(cfg, "nes", tmp_path / "data", fake_report(calls))
    assert [inputs for inputs, _ in calls] == [[tmp_path / "inbox"]]
    with state.State(tmp_path / "data" / "state.db") as database:
        assert database.counts()["nes"] == state.Counts(have=0, inbox=1, missing=2, unmatched=0)


def test_scan_platform_applies_include(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, library=True, include=("unlicensed",))
    write_dat(tmp_path, cfg)
    scan.scan_platform(cfg, "nes", tmp_path / "data", fake_report([]))
    with state.State(tmp_path / "data" / "state.db") as database:
        assert database.missing("nes") == ["C (USA)"]
        assert [match.state for match in lookup.by_name(database, "nes", "C (USA) (Unl)")] == [
            "missing"
        ]


def test_scan_platform_indexes_the_dat_before_reading_it(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, library=True)
    write_dat(tmp_path, cfg)
    scan.scan_platform(cfg, "nes", tmp_path / "data", fake_report([]))
    with state.State(tmp_path / "data" / "state.db") as database:
        assert len(database.dat_roms("nes")) == len(GAMES)


def test_require_dats(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, library=True)
    with pytest.raises(config.ConfigError, match=r"no DAT for nes .*dats update"):
        scan.require_dats(cfg, ["nes"], tmp_path / "data")
    write_dat(tmp_path, cfg)
    scan.require_dats(cfg, ["nes"], tmp_path / "data")
