from collections.abc import Sequence
from pathlib import Path

import pytest

from romledger import config, dats, igir, registry, scan, state

ReportRow = igir.ReportRow


def row(status: str, game: str = "", path: str = "") -> ReportRow:
    return ReportRow("Nintendo", status, game, path)


def test_library_found_is_have() -> None:
    items, unmatched = scan.classify([row("FOUND", "A", "/l/A")], [])
    assert items == [state.Item("A", "have", "/l/A")]
    assert unmatched == []


def test_inbox_found_not_in_library_is_inbox() -> None:
    items, _ = scan.classify([row("MISSING", "A")], [row("FOUND", "A", "/i/A")])
    assert items == [state.Item("A", "inbox", "/i/A")]


def test_game_in_both_is_have() -> None:
    items, _ = scan.classify([row("FOUND", "A", "/l/A")], [row("FOUND", "A", "/i/A")])
    assert items == [state.Item("A", "have", "/l/A")]


def test_remaining_missing() -> None:
    items, _ = scan.classify([row("MISSING", "A")], [row("MISSING", "A")])
    assert items == [state.Item("A", "missing", None)]


def test_library_unused_is_unmatched_inbox_unused_ignored() -> None:
    _, unmatched = scan.classify([row("UNUSED", path="/l/x")], [row("UNUSED", path="/i/y")])
    assert unmatched == ["/l/x"]


def make_config(tmp_path: Path, *, library: bool) -> config.Config:
    roms, inbox = tmp_path / "roms", tmp_path / "inbox"
    inbox.mkdir()
    if library:
        (roms / "nes").mkdir(parents=True)
    return config.Config(
        config.Library(roms, (inbox,)),
        {"nes": config.Platform(registry.load()["nes"].dat)},
    )


def fake_report(calls: list[tuple[list[Path], Sequence[str]]]) -> scan.IgirReport:
    def report(
        dats: list[Path],
        inputs: list[Path],
        cache: Path,
        filters: igir.Filters | None,
        excludes: Sequence[str],
    ) -> list[ReportRow]:
        calls.append((list(inputs), excludes))
        assert len(dats) == 1
        assert filters == igir.Filters(("USA", "WORLD"), ("EN",))
        if inputs[0].name == "inbox":
            return [row("FOUND", "B", "/i/B"), row("MISSING", "A"), row("MISSING", "C")]
        return [row("FOUND", "A", "/l/A"), row("MISSING", "B"), row("UNUSED", path="/l/x")]

    return report


def write_dat(tmp_path: Path, cfg: config.Config) -> None:
    path = dats.dat_path(tmp_path / "data", cfg.platforms["nes"].dat)
    path.parent.mkdir(parents=True)
    path.write_text('clrmamepro (\n\tversion "2026.10.01"\n)\n')


def test_scan_platform_with_library(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, library=True)
    write_dat(tmp_path, cfg)
    calls: list[tuple[list[Path], Sequence[str]]] = []
    scan.scan_platform(cfg, "nes", tmp_path / "data", fake_report(calls))
    inbox = tmp_path / "inbox"
    assert calls == [
        ([inbox], (f"{inbox}/unmatched/**", f"{inbox}/duplicates/**")),
        ([tmp_path / "roms" / "nes"], ()),
    ]
    with state.State(tmp_path / "data" / "state.db") as database:
        assert database.counts()["nes"] == state.Counts(have=1, inbox=1, missing=0, unmatched=1)


def test_scan_platform_without_library_dir(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, library=False)
    write_dat(tmp_path, cfg)
    calls: list[tuple[list[Path], Sequence[str]]] = []
    scan.scan_platform(cfg, "nes", tmp_path / "data", fake_report(calls))
    assert [inputs for inputs, _ in calls] == [[tmp_path / "inbox"]]
    with state.State(tmp_path / "data" / "state.db") as database:
        assert database.counts()["nes"] == state.Counts(have=0, inbox=1, missing=2, unmatched=0)


def test_require_dats(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, library=True)
    with pytest.raises(config.ConfigError, match=r"no DAT for nes .*dats update"):
        scan.require_dats(cfg, ["nes"], tmp_path / "data")
    write_dat(tmp_path, cfg)
    scan.require_dats(cfg, ["nes"], tmp_path / "data")
