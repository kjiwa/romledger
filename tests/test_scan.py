from collections.abc import Sequence
from pathlib import Path

import httpx
import pytest

from romledger import catalog, config, dats, igir, lookup, registry, scan, state

ReportRow = igir.ReportRow
NES = "Nintendo - Nintendo Entertainment System"


def row(status: str, game: str = "", path: str = "", dat: str = NES) -> ReportRow:
    return ReportRow(dat, status, game, path)


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
DAT = f'clrmamepro (\n\tname "{NES}"\n\tversion "2026.10.01"\n)\n' + "".join(
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


def serving(content: dict[str, str], requested: list[str] | None = None) -> scan.ClientFactory:
    def handler(request: httpx.Request) -> httpx.Response:
        if requested is not None:
            requested.append(request.url.path.rsplit("/", 1)[-1])
        text = content.get(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, text=text) if text else httpx.Response(404)

    return lambda proxy: httpx.Client(transport=httpx.MockTransport(handler))


def test_ensure_dats_downloads_only_what_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = make_config(tmp_path, library=True)
    write_dat(tmp_path, cfg)
    snes = registry.load()["snes"].dat
    cfg = config.Config(cfg.library, {**cfg.platforms, "snes": config.Platform(snes)})
    requested: list[str] = []
    factory = serving({"Nintendo - Super Nintendo Entertainment System.dat": DAT}, requested)
    assert scan.ensure_dats(cfg, ["nes", "snes"], tmp_path / "data", factory) == ["nes", "snes"]
    assert requested == ["Nintendo - Super Nintendo Entertainment System.dat"]
    assert dats.dat_path(tmp_path / "data", snes).is_file()
    assert "downloading the snes DAT" in capsys.readouterr().err


def test_ensure_dats_opens_no_connection_when_every_dat_exists(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, library=True)
    write_dat(tmp_path, cfg)

    def refuse(proxy: str | None) -> httpx.Client:
        raise AssertionError("opened a client")

    assert scan.ensure_dats(cfg, ["nes"], tmp_path / "data", refuse) == ["nes"]


def test_ensure_dats_skips_a_platform_whose_dat_cannot_be_downloaded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = make_config(tmp_path, library=True)
    write_dat(tmp_path, cfg)
    cfg = config.Config(
        cfg.library, {**cfg.platforms, "snes": config.Platform(registry.load()["snes"].dat)}
    )
    assert scan.ensure_dats(cfg, ["nes", "snes"], tmp_path / "data", serving({})) == ["nes"]
    assert "warning: skipping snes: " in capsys.readouterr().err


def test_ensure_dats_fails_when_none_can_be_downloaded(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, library=True)
    with pytest.raises(config.ConfigError, match=r"no DAT could be downloaded \(1 failed\)"):
        scan.ensure_dats(cfg, ["nes"], tmp_path / "data", serving({}))


def test_scan_platforms_reads_the_inbox_once_and_splits_rows_by_dat(tmp_path: Path) -> None:
    roms, inbox = tmp_path / "roms", tmp_path / "inbox"
    inbox.mkdir()
    entries = registry.load()
    cfg = config.Config(
        config.Library(roms, (inbox,)),
        {slug: config.Platform(entries[slug].dat) for slug in ("nes", "snes")},
    )
    other = "Nintendo - Super Nintendo Entertainment System"
    for slug, name in (("nes", NES), ("snes", other)):
        path = dats.dat_path(tmp_path / "data", cfg.platforms[slug].dat)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DAT.replace(NES, name, 1))
    calls: list[list[Path]] = []

    def report(
        files: list[Path], inputs: list[Path], cache: Path, excludes: Sequence[str]
    ) -> list[ReportRow]:
        calls.append(list(inputs))
        return [row("FOUND", "A (USA)", "/i/A", NES), row("FOUND", "B (USA)", "/i/B", other)]

    seen: list[str] = []
    scan.scan_platforms(cfg, ["nes", "snes"], tmp_path / "data", report, seen.append)
    assert calls == [[inbox]]
    assert seen == ["inbox", "nes", "snes"]
    with state.State(tmp_path / "data" / "state.db") as database:
        assert database.counts()["nes"].inbox == 1
        assert database.counts()["snes"].inbox == 1
        assert database.missing("nes") == ["B (USA)", "C (USA)"]
        assert database.missing("snes") == ["A (USA)", "C (USA)"]


def test_scan_platforms_with_no_platforms_does_nothing(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, library=True)

    def report(*args: object) -> list[ReportRow]:
        raise AssertionError("ran igir")

    scan.scan_platforms(cfg, [], tmp_path / "data", report)
