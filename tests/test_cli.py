import dataclasses
import json
import os
import webbrowser
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from romledger import (
    __version__,
    canary,
    cli,
    config,
    dats,
    fetch,
    http,
    importer,
    registry,
    scan,
    state,
    term,
)
from romledger.context import Context
from romledger.sources.base import Candidate
from romledger.web import app as web_app


@pytest.fixture(autouse=True)
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "data"
    monkeypatch.setenv(config.DATA_ENV, str(path))
    return path


def make_config(tmp_path: Path, *, mkdirs: bool = True) -> Path:
    if mkdirs:
        (tmp_path / "roms").mkdir()
        (tmp_path / "inbox").mkdir()
    path = tmp_path / "config.toml"
    path.write_text(
        f'[library]\nroms = "{tmp_path / "roms"}"\ninboxes = ["{tmp_path / "inbox"}"]\n'
    )
    return path


def no_dats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        http, "client", lambda proxy=None: httpx.Client(transport=httpx.MockTransport(not_found))
    )


def not_found(request: httpx.Request) -> httpx.Response:
    return httpx.Response(404)


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"romledger {__version__}"


def test_config_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = make_config(tmp_path)
    assert cli.main(["--config", str(path), "config"]) == 0
    out = capsys.readouterr().out
    assert str(path) in out
    assert "wanted:  regions USA, WORLD; languages EN\n" in out
    assert "nes:" not in out
    assert "include" not in out
    assert out.isascii()


def test_config_summary_lists_included_categories(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = make_config(tmp_path)
    path.write_text(path.read_text() + '[wanted]\ninclude = ["unlicensed", "bad"]\n')
    assert cli.main(["--config", str(path), "config"]) == 0
    assert "; include unlicensed, bad\n" in capsys.readouterr().out


def test_config_summary_lists_only_platforms_that_differ(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = make_config(tmp_path)
    path.write_text(path.read_text() + '[platforms.snes]\nregions = ["JPN"]\n[platforms.nes]\n')
    assert cli.main(["--config", str(path), "config"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "snes:  regions JPN; languages EN" in lines
    assert [line for line in lines if line.startswith(("nes:", "gb:"))] == []


def test_config_error_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = make_config(tmp_path, mkdirs=False)
    assert cli.main(["--config", str(path), "config"]) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("romledger: error: ")
    assert "drive or share mounted" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_missing_config_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--config", str(tmp_path / "nope.toml"), "config"]) == 2
    err = capsys.readouterr().err
    assert "not found" in err
    assert "romledger init" in err


def seed(data_dir: Path, platform: str, items: list[state.Item]) -> None:
    with state.State(data_dir / "state.db") as database:
        database.replace_platform(platform, items, ["/u"], "v", "t")


def run(path: Path, *args: str) -> int:
    return cli.main(["--config", str(path), *args])


def test_config_shows_data_dir(
    tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(make_config(tmp_path), "config") == 0
    assert f"data:    {data_dir}" in capsys.readouterr().out


def test_status_shows_only_platforms_that_have_games(
    tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(
        data_dir,
        "nes",
        [state.Item("A", "have", "/a"), state.Item("B", "inbox", "/b")]
        + [state.Item(f"M{n}", "missing", None) for n in range(2)],
    )
    seed(data_dir, "snes", [state.Item("A", "missing", None)])
    assert run(make_config(tmp_path), "status") == 0
    assert capsys.readouterr().out == (
        "platform  wanted  have  inbox  missing  unmatched  done\n"
        "nes            4     1      1        2          1   25%\n"
        f"{len(registry.load()) - 1} platforms with no games hidden; romledger status --all\n"
    )


def test_status_all_lists_every_platform(
    tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(data_dir, "nes", [state.Item("A", "have", "/a")])
    assert run(make_config(tmp_path), "status", "--all") == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == len(registry.load()) + 2
    assert lines[1].startswith("atari2600  ")
    assert lines[1].endswith("-")
    assert lines[-1] == "run: romledger scan"


def test_status_before_any_scan_says_to_scan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(make_config(tmp_path), "status") == 0
    assert capsys.readouterr().out == "run: romledger scan\n"


def test_status_with_no_games_says_to_import(
    tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(data_dir, "nes", [state.Item("A", "missing", None)])
    assert run(make_config(tmp_path), "status") == 0
    assert capsys.readouterr().out == (
        "no games yet; put ROMs in an inbox and run: romledger import\n"
    )


def test_status_with_every_platform_tracked_has_no_footer(
    tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for slug in registry.load():
        seed(data_dir, slug, [state.Item("A", "have", "/a")])
    assert run(make_config(tmp_path), "status") == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == len(registry.load()) + 1


def test_missing_lists_games(
    tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    items = [state.Item("Zed (USA)", "missing", None), state.Item("Ant (USA)", "missing", None)]
    seed(data_dir, "nes", items)
    assert run(make_config(tmp_path), "missing", "nes") == 0
    assert capsys.readouterr().out == "Ant (USA)\nZed (USA)\n"


def test_missing_links(tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    items = [
        state.Item("Super Mario Bros. (USA)", "missing", None),
        state.Item("R (USA)", "missing", None),
    ]
    seed(data_dir, "nes", items)
    assert run(make_config(tmp_path), "missing", "nes", "--links") == 0
    assert capsys.readouterr().out.splitlines() == [
        "R (USA)",
        "Super Mario Bros. (USA)\thttps://vimm.net/vault/?p=list&system=NES&q=Super+Mario+Bros.",
    ]


def test_missing_links_leaves_a_game_bare_when_vimm_lacks_the_platform(
    tmp_path: Path,
    data_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = registry.load()
    real["nes"] = dataclasses.replace(real["nes"], vimm=None)
    monkeypatch.setattr(registry, "load", lambda: real)
    seed(data_dir, "nes", [state.Item("Contra (USA)", "missing", None)])
    assert run(make_config(tmp_path), "missing", "nes", "--links") == 0
    assert capsys.readouterr().out == "Contra (USA)\n"


def test_missing_links_without_site_codes(
    tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(data_dir, "neo-geo-pocket-color", [state.Item("Game (USA)", "missing", None)])
    assert run(make_config(tmp_path), "missing", "neo-geo-pocket-color", "--links") == 0
    assert capsys.readouterr().out == "Game (USA)\n"


def test_missing_unscanned(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(make_config(tmp_path), "missing", "nes") == 2
    assert "nes has not been scanned. run: romledger scan" in capsys.readouterr().err


def test_unknown_platform_suggests_the_nearest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(make_config(tmp_path), "missing", "snez") == 2
    assert "unknown platform 'snez'. Nearest: snes" in capsys.readouterr().err


def test_scan_downloads_dats_and_fails_when_none_can_be_fetched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    no_dats(monkeypatch)
    assert run(make_config(tmp_path), "scan", "nes") == 2
    err = capsys.readouterr().err
    assert "downloading the nes DAT ..." in err
    assert "romledger: error: no DAT could be downloaded (1 failed)" in err


def test_scan_runs_the_named_platform(
    tmp_path: Path,
    data_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = make_config(tmp_path)
    dat = dats.dat_path(data_dir, "no-intro/Nintendo - Nintendo Entertainment System")
    dat.parent.mkdir(parents=True)
    dat.write_text("x")
    scanned: list[str] = []

    def fake_scan(
        cfg: config.Config, slugs: list[str], data: Path, progress: Callable[[str], None]
    ) -> None:
        scanned.extend(slugs)
        progress("inbox")
        progress("nes")

    monkeypatch.setattr(scan, "scan_platforms", fake_scan)
    assert run(path, "scan", "nes", "nes") == 0
    captured = capsys.readouterr()
    assert scanned == ["nes"]
    assert captured.err == "scanning inbox ...\nscanning nes ...\n"
    assert captured.out == "scanned 1 platform(s)\n"


def test_scan_covers_every_platform_by_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    scanned: list[str] = []
    monkeypatch.setattr(scan, "ensure_dats", lambda cfg, slugs, data: slugs)
    monkeypatch.setattr(
        scan, "scan_platforms", lambda cfg, slugs, data, progress: scanned.extend(slugs)
    )
    assert run(make_config(tmp_path), "scan") == 0
    assert scanned == list(registry.load())
    assert capsys.readouterr().out == f"scanned {len(registry.load())} platform(s)\n"


def test_dats_update_output(
    tmp_path: Path,
    data_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_update(
        directory: Path, wanted: dict[str, str], client: object
    ) -> dict[str, dats.Result]:
        assert wanted == {"nes": "no-intro/Nintendo - Nintendo Entertainment System"}
        return {"nes": dats.Result(directory / "x", "2026.10.01", changed=True)}

    monkeypatch.setattr(dats, "update", fake_update)
    assert run(make_config(tmp_path), "dats", "update", "nes") == 0
    assert capsys.readouterr().out == "nes 2026.10.01 (updated)\n"


def test_dats_error_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object) -> dict[str, dats.Result]:
        raise dats.DatError("http://x: HTTP 404. Fix it.")

    monkeypatch.setattr(dats, "update", fail)
    assert run(make_config(tmp_path), "dats", "update") == 2
    assert "romledger: error: http://x: HTTP 404" in capsys.readouterr().err


def test_broken_pipe_exits_quietly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    def broken(args: object) -> int:
        raise BrokenPipeError

    redirected: list[int] = []
    monkeypatch.setattr(os, "dup2", lambda source, target: redirected.append(target))
    monkeypatch.setitem(cli.HANDLERS, "status", broken)
    assert run(make_config(tmp_path), "status") == 0
    assert len(redirected) == 1


def fake_import(result: importer.ImportResult, calls: list[bool]) -> object:
    def import_inboxes(cfg: config.Config, data: Path, dry_run: bool) -> importer.ImportResult:
        calls.append(dry_run)
        return result

    return import_inboxes


def test_import_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bool] = []
    result = importer.ImportResult(
        {"nes": 2, "snes": 1}, [Path("a")], [Path("w")], [Path("b"), Path("c")], [], [Path("e")]
    )
    monkeypatch.setattr(importer, "import_inboxes", fake_import(result, calls))
    assert run(make_config(tmp_path), "import") == 0
    out = capsys.readouterr().out
    assert out == (
        "moved nes 2\nmoved snes 1\n"
        "extracted 1 (moved to <inbox>/extracted)\n"
        "duplicates 1 (moved to <inbox>/duplicates)\n"
        "unwanted 1 (moved to <inbox>/unwanted)\n"
        "unmatched 2 (moved to <inbox>/unmatched)\n"
    )
    assert out.isascii()
    assert calls == [False]


def test_import_dry_run_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bool] = []
    result = importer.ImportResult({"nes": 2}, [], [], [Path("b")], [])
    monkeypatch.setattr(importer, "import_inboxes", fake_import(result, calls))
    assert run(make_config(tmp_path), "import", "--dry-run") == 0
    assert capsys.readouterr().out == (
        "would move nes 2\nunmatched 1 (would move to <inbox>/unmatched)\n"
    )
    assert calls == [True]


def test_import_empty_inbox(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = importer.ImportResult({}, [], [], [], [])
    monkeypatch.setattr(importer, "import_inboxes", fake_import(result, []))
    assert run(make_config(tmp_path), "import") == 0
    assert capsys.readouterr().out == "inbox is empty\n"


def test_import_hook_failure_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = importer.ImportResult({"nes": 1}, [], [], [], ["touch x: exit status 1"])
    monkeypatch.setattr(importer, "import_inboxes", fake_import(result, []))
    assert run(make_config(tmp_path), "import") == 1
    captured = capsys.readouterr()
    assert captured.out == "moved nes 1\n"
    assert captured.err == "romledger: error: after_import hook failed: touch x: exit status 1\n"


def test_import_without_any_dat_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    no_dats(monkeypatch)
    assert run(make_config(tmp_path), "import") == 2
    assert "no DAT could be downloaded" in capsys.readouterr().err


def test_config_lists_hooks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = make_config(tmp_path)
    path.write_text(path.read_text() + '[hooks]\nafter_import = [["touch", "/x"]]\n')
    assert run(path, "config") == 0
    assert "hook:    after_import touch /x" in capsys.readouterr().out


def test_os_error_is_a_clean_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing(args: object) -> int:
        raise PermissionError("denied")

    monkeypatch.setitem(cli.HANDLERS, "status", failing)
    assert run(make_config(tmp_path), "status") == 2
    assert capsys.readouterr().err == "romledger: error: denied\n"


def sources_config(tmp_path: Path, extra: str = "") -> Path:
    path = make_config(tmp_path)
    path.write_text(path.read_text() + extra)
    return path


def test_config_lists_the_proxy_without_its_password(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = sources_config(tmp_path, '[network]\nproxy = "http://alice:secret@proxy.example:3128"\n')
    assert run(path, "config") == 0
    out = capsys.readouterr().out
    assert "proxy:   http://***@proxy.example:3128" in out
    assert "secret" not in out
    assert out.isascii()


def test_config_without_a_proxy_prints_none(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(make_config(tmp_path), "config") == 0
    assert "proxy:" not in capsys.readouterr().out


def test_fetch_needs_a_source_that_carries_the_platform(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(make_config(tmp_path), "fetch", "neo-geo-pocket-color") == 2
    assert capsys.readouterr().err == (
        "romledger: error: no source can fetch neo-geo-pocket-color. "
        "Download it by hand into an inbox.\n"
    )


def test_fetch_unknown_platform(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(sources_config(tmp_path), "fetch", "snez") == 2
    assert "unknown platform 'snez'. Nearest: snes" in capsys.readouterr().err


def test_fetch_unscanned(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(sources_config(tmp_path), "fetch", "atari7800") == 2
    assert capsys.readouterr().err.rstrip().endswith("run: romledger scan")


def test_fetch_source_that_cannot_be_fetched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(make_config(tmp_path), "fetch", "snes", "--source", "vimm") == 2
    assert capsys.readouterr().err == (
        "romledger: error: Vimm's Lair cannot be fetched from the command line; "
        "download from it with the browser extension.\n"
    )


def test_fetch_unknown_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(make_config(tmp_path), "fetch", "--source", "coolrom") == 2
    assert "unknown source 'coolrom'. Sources: vimm, consoleroms." in capsys.readouterr().err


def test_fetch_defaults_to_the_platforms_that_have_games(
    tmp_path: Path,
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = harness(monkeypatch, fetched=["A (USA)"])
    seed(data_dir, "atari7800", [state.Item("A (USA)", "have", "/a")])
    seed(data_dir, "snes", [state.Item("B (USA)", "have", "/b")])
    seed(data_dir, "gb", [state.Item("C (USA)", "missing", None)])
    seed(data_dir, "neo-geo-pocket-color", [state.Item("D (USA)", "have", "/d")])
    assert run(make_config(tmp_path), "fetch") == 0
    assert [call[1] for call in fake.calls] == ["snes", "atari7800"] or [
        call[1] for call in fake.calls
    ] == ["atari7800", "snes"]
    assert capsys.readouterr().err.splitlines() == [
        f"fetching {call[1]} ..." for call in fake.calls
    ]


def test_fetch_stops_at_the_limit_across_platforms(
    tmp_path: Path, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = harness(monkeypatch, fetched=["A (USA)", "B (USA)"])
    seed(data_dir, "atari7800", [state.Item("A (USA)", "have", "/a")])
    seed(data_dir, "snes", [state.Item("B (USA)", "have", "/b")])
    seed(data_dir, "nes", [state.Item("C (USA)", "have", "/c")])
    assert run(make_config(tmp_path), "fetch", "--limit", "3") == 0
    assert [call[3] for call in fake.calls] == [3, 1]


def test_fetch_with_nothing_to_fetch(
    tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(data_dir, "neo-geo-pocket-color", [state.Item("D (USA)", "have", "/d")])
    assert run(make_config(tmp_path), "fetch") == 0
    assert capsys.readouterr().out.startswith("nothing to fetch")


def test_fetch_with_a_source_skips_platforms_it_does_not_carry(
    tmp_path: Path, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = harness(monkeypatch, not_found=["A (USA)"])
    seed(data_dir, "snes", [state.Item("B (USA)", "have", "/b")])
    seed(data_dir, "3ds", [state.Item("C (USA)", "have", "/c")])
    assert run(make_config(tmp_path), "fetch", "--source", "consoleroms") == 0
    assert [call[1] for call in fake.calls] == ["snes"]


@pytest.mark.parametrize("limit", ["0", "-1", "x"])
def test_fetch_limit_must_be_positive(limit: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["fetch", "nes", "--limit", limit])
    assert exit_info.value.code == 2
    assert "positive integer" in capsys.readouterr().err


class FetchHarness:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, result: fetch.FetchResult) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.imports: list[bool] = []
        self.hook_failures: list[str] = []

        def fake_fetch(*args: object) -> fetch.FetchResult:
            self.calls.append(args)
            return result

        def fake_import(cfg: object, data: object, dry_run: bool) -> importer.ImportResult:
            self.imports.append(dry_run)
            return importer.ImportResult({"atari7800": 1}, [], [], [], self.hook_failures)

        monkeypatch.setattr(fetch, "fetch_platform", fake_fetch)
        monkeypatch.setattr(importer, "import_inboxes", fake_import)


def harness(monkeypatch: pytest.MonkeyPatch, **fields: list[str]) -> FetchHarness:
    return FetchHarness(monkeypatch, fetch.FetchResult(**fields))  # type: ignore[arg-type]


def test_fetch_imports_after_a_successful_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = harness(monkeypatch, fetched=["A (USA)"])
    assert (
        run(
            sources_config(tmp_path),
            "fetch",
            "atari7800",
            "--limit",
            "5",
            "--source",
            "consoleroms",
        )
        == 0
    )
    assert fake.imports == [False]
    args = fake.calls[0]
    assert args[1:4] == ("atari7800", config.data_dir(), 5)
    assert args[4] is False
    assert args[-1] == "consoleroms"
    assert capsys.readouterr().out == "moved atari7800 1\n"


def test_fetch_exit_code_when_a_game_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = harness(monkeypatch, fetched=["A (USA)"])
    fake_failed = fetch.FetchResult(["A (USA)"], [], [("B (USA)", "boom")], [])
    monkeypatch.setattr(fetch, "fetch_platform", lambda *args: fake_failed)
    assert run(sources_config(tmp_path), "fetch", "atari7800") == 1
    assert fake.imports == [False]


def test_fetch_without_downloads_does_not_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = harness(monkeypatch, not_found=["A (USA)"])
    assert run(sources_config(tmp_path), "fetch", "atari7800") == 0
    assert fake.imports == []


def test_fetch_no_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = harness(monkeypatch, fetched=["A (USA)"])
    assert run(sources_config(tmp_path), "fetch", "atari7800", "--no-import") == 0
    assert fake.imports == []


def test_fetch_dry_run_does_not_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = harness(monkeypatch, fetched=["A (USA)"])
    assert run(sources_config(tmp_path), "fetch", "atari7800", "--dry-run") == 0
    assert fake.imports == []
    assert fake.calls[0][4] is True


def test_fetch_blocked_source_is_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = harness(monkeypatch, blocked=["https://c/x: not fetched, robots"])
    assert run(sources_config(tmp_path), "fetch", "atari7800") == 0
    assert fake.imports == []


def test_fetch_reports_a_failed_import_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = harness(monkeypatch, fetched=["A (USA)"])
    fake.hook_failures.append("touch x: exit status 1")
    assert run(sources_config(tmp_path), "fetch", "atari7800") == 1
    assert "after_import hook failed" in capsys.readouterr().err


def test_fetch_end_to_end(
    tmp_path: Path,
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seed(
        data_dir,
        "atari7800",
        [state.Item("A (USA)", "missing", None), state.Item("B (USA)", "missing", None)],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"abc")

    class Stub:
        name = "consoleroms"

        def find(self, game: str) -> Candidate | None:
            if game != "A (USA)":
                return None
            return Candidate(game, lambda: "https://dl.example/A.zip", "A (USA).zip", 3)

    monkeypatch.setattr(fetch, "build_sources", lambda platform, names, client, throttle: [Stub()])

    monkeypatch.setattr(
        http, "client", lambda proxy=None: httpx.Client(transport=httpx.MockTransport(handler))
    )
    throttle = http.Throttle
    monkeypatch.setattr(http, "Throttle", lambda: throttle(sleep=lambda _: None))
    monkeypatch.setattr(
        importer, "import_inboxes", lambda *args: importer.ImportResult({}, [], [], [], [])
    )
    assert run(make_config(tmp_path), "fetch", "atari7800", "--no-import") == 0
    assert (tmp_path / "inbox" / "A (USA).zip").read_bytes() == b"abc"
    assert capsys.readouterr().out.splitlines() == [
        "fetched A (USA) (consoleroms)",
        "not found B (USA)",
        "fetched 1, not found 1, failed 0, skipped 0",
    ]


def test_dats_update_uses_the_configured_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxies: list[str | None] = []

    def fake_client(proxy: str | None = None) -> httpx.Client:
        proxies.append(proxy)
        return httpx.Client()

    monkeypatch.setattr(http, "client", fake_client)
    monkeypatch.setattr(dats, "update", lambda *args: {})
    path = make_config(tmp_path)
    path.write_text(path.read_text() + '[network]\nproxy = "http://proxy.example:3128"\n')
    assert run(path, "dats", "update") == 0
    assert proxies == ["http://proxy.example:3128"]


def fake_canary(monkeypatch: pytest.MonkeyPatch, report: canary.Report) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def run(*args: object, **kwargs: object) -> canary.Report:
        calls.append(kwargs)
        return report

    monkeypatch.setattr(canary, "run", run)
    return calls


FINDING = canary.Finding("vimm:new-platform:Amiga", "vimm lists Amiga", "Add it.")
NOTE = "https://a.example/: HTTP 403"


def test_canary_all_clear(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "t0ken")
    calls = fake_canary(monkeypatch, canary.Report([], [], []))
    assert cli.main(["canary"]) == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")
    assert calls == [{"token": "t0ken"}]


def test_canary_findings_exit_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_canary(monkeypatch, canary.Report([FINDING], [NOTE], ["vimm", "vimm:contract:list"]))
    assert cli.main(["canary"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "finding vimm:new-platform:Amiga: vimm lists Amiga",
        f"note: {NOTE}",
        "unverified vimm",
        "unverified vimm:contract:list",
    ]


def test_canary_notes_alone_exit_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_canary(monkeypatch, canary.Report([], [NOTE], ["igir"]))
    assert cli.main(["canary"]) == 0
    assert capsys.readouterr().out == f"note: {NOTE}\nunverified igir\n"


def test_canary_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fake_canary(monkeypatch, canary.Report([FINDING], [NOTE], ["igir"]))
    assert cli.main(["canary", "--json"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "findings": [
            {"key": "vimm:new-platform:Amiga", "title": "vimm lists Amiga", "detail": "Add it."}
        ],
        "inconclusive": ["igir"],
    }
    assert captured.err == f"note: {NOTE}\n"


def test_canary_json_without_findings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_canary(monkeypatch, canary.Report([], [], []))
    assert cli.main(["canary", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"findings": [], "inconclusive": []}


def test_canary_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["canary", "--bogus"])
    assert exit_info.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_platforms_lists_every_platform_without_a_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--config", str(tmp_path / "none.toml"), "platforms"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["platform", "name", "dat", "sources"]
    assert len(lines) == len(registry.load()) + 1
    snes = next(line for line in lines if line.startswith("snes "))
    assert snes.split(maxsplit=1)[1].startswith("Nintendo - Super Nintendo Entertainment System")
    assert snes.endswith("no-intro  vimm, consoleroms")
    assert all(line.isascii() for line in lines)


def test_platforms_columns_line_up(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["platforms"]) == 0
    lines = capsys.readouterr().out.splitlines()
    offsets = {line.index("no-intro") for line in lines if "no-intro" in line}
    assert len(offsets) == 1
    assert lines[0].index("dat") == offsets.pop()


def test_platforms_is_cut_to_the_terminal_width(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(term, "width", lambda: 80)
    assert cli.main(["platforms"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert max(len(line) for line in lines) <= 80
    assert any("…" in line for line in lines)


def test_platforms_names_every_source_that_carries_a_platform(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["platforms"]) == 0
    out = capsys.readouterr().out
    assert next(line for line in out.splitlines() if line.startswith("atari7800 ")).endswith(
        "vimm, consoleroms"
    )
    assert next(
        line for line in out.splitlines() if line.startswith("neo-geo-pocket-color ")
    ).endswith("no-intro  -")


def test_serve_prints_the_link_and_runs_uvicorn(
    tmp_path: Path,
    data_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    opened: list[str] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(webbrowser, "open", opened.append)
    path = make_config(tmp_path)
    assert run(path, "serve") == 0
    token = (data_dir / "serve.token").read_text().strip()
    assert capsys.readouterr().out == f"romledger dashboard: http://127.0.0.1:8730/?token={token}\n"
    assert calls == [{"host": "127.0.0.1", "port": 8730, "access_log": False}]
    assert opened == []
    assert run(path, "serve", "--host", "192.0.2.10", "--port", "9000", "--open") == 0
    assert opened == [f"http://192.0.2.10:9000/?token={token}"]
    assert calls[1]["host"] == "192.0.2.10"
    assert calls[1]["port"] == 9000


def test_serve_imports_automatically_unless_told_not_to(
    tmp_path: Path, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flags: list[bool] = []
    create = web_app.create_app

    def record(factory: Callable[[], Context], token: str, *, auto_import: bool) -> FastAPI:
        flags.append(auto_import)
        return create(factory, token, auto_import=auto_import)

    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: None)
    monkeypatch.setattr("romledger.cli.create_app", record)
    path = make_config(tmp_path)
    assert run(path, "serve") == 0
    assert run(path, "serve", "--no-auto-import") == 0
    assert flags == [True, False]


@pytest.mark.parametrize("host", cli.WILDCARD_HOSTS)
def test_serve_links_localhost_for_a_wildcard_bind(
    tmp_path: Path,
    data_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    host: str,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    assert run(make_config(tmp_path), "serve", "--host", host) == 0
    token = (data_dir / "serve.token").read_text().strip()
    assert capsys.readouterr().out == f"romledger dashboard: http://localhost:8730/?token={token}\n"
    assert calls[0]["host"] == host


def test_serve_reports_an_unmounted_library(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(make_config(tmp_path, mkdirs=False), "serve") == 2
    assert "drive or share mounted" in capsys.readouterr().err


@pytest.mark.parametrize("port", ["0", "70000", "abc", "-1"])
def test_serve_rejects_bad_ports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], port: str
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        run(make_config(tmp_path), "serve", "--port", port)
    assert exit_info.value.code == 2
    assert "not a port between 1 and 65535" in capsys.readouterr().err
