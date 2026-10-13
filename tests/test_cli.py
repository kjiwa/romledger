import os
from pathlib import Path

import pytest

from rom_scraper import __version__, cli, config, dats, importer, scan, state


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
        "[platforms.nes]\n"
    )
    return path


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"rom-scraper {__version__}"


def test_config_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = make_config(tmp_path)
    assert cli.main(["--config", str(path), "config"]) == 0
    out = capsys.readouterr().out
    assert str(path) in out
    assert "nes: no-intro/Nintendo - Nintendo Entertainment System" in out
    assert "  regions: USA, WORLD" in out
    assert "  languages: EN" in out
    assert out.isascii()


def test_config_error_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = make_config(tmp_path, mkdirs=False)
    assert cli.main(["--config", str(path), "config"]) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("rom-scraper: error: ")
    assert "NAS share mounted" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_missing_config_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--config", str(tmp_path / "nope.toml"), "config"]) == 2
    assert "not found" in capsys.readouterr().err


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


def test_status_golden(tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = make_config(tmp_path)
    path.write_text(path.read_text() + "[platforms.snes]\n")
    seed(
        data_dir,
        "nes",
        [state.Item("A", "have", "/a"), state.Item("B", "inbox", "/b")]
        + [state.Item(f"M{n}", "missing", None) for n in range(2)],
    )
    assert run(path, "status") == 0
    assert capsys.readouterr().out == (
        "platform  wanted  have  inbox  missing  unmatched  done\n"
        "nes            4     1      1        2          1   25%\n"
        "snes           -     -      -        -          -     -\n"
        "run: rom-scraper scan\n"
    )


def test_status_all_scanned_has_no_hint(
    tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(data_dir, "nes", [])
    assert run(make_config(tmp_path), "status") == 0
    out = capsys.readouterr().out
    assert "scan" not in out
    assert out.splitlines()[1].endswith("-")


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


def test_missing_links_without_vimm_code(
    tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = make_config(tmp_path)
    path.write_text(
        path.read_text().replace("[platforms.nes]", "[platforms.custom]") + 'dat = "redump/X"\n'
    )
    seed(data_dir, "custom", [state.Item("Game (USA)", "missing", None)])
    assert run(path, "missing", "custom", "--links") == 0
    assert capsys.readouterr().out == "Game (USA)\n"


def test_missing_unscanned(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(make_config(tmp_path), "missing", "nes") == 2
    assert "nes has not been scanned. run: rom-scraper scan" in capsys.readouterr().err


def test_unknown_platform_lists_configured(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(make_config(tmp_path), "missing", "snes") == 2
    err = capsys.readouterr().err
    assert "unknown platform 'snes'. Configured platforms: nes." in err


def test_scan_without_dat_prints_fix(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(make_config(tmp_path), "scan") == 2
    err = capsys.readouterr().err
    assert err.startswith("rom-scraper: error: no DAT for nes")
    assert err.rstrip().endswith("run: rom-scraper dats update")


def test_scan_runs_each_platform(
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
    monkeypatch.setattr(scan, "scan_platform", lambda cfg, slug, data: scanned.append(slug))
    assert run(path, "scan", "nes", "nes") == 0
    captured = capsys.readouterr()
    assert scanned == ["nes"]
    assert captured.err == "scanning nes ...\n"
    assert captured.out == "scanned 1 platform(s)\n"


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
    assert "rom-scraper: error: http://x: HTTP 404" in capsys.readouterr().err


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
    result = importer.ImportResult({"nes": 2, "snes": 1}, [Path("a")], [Path("b"), Path("c")], [])
    monkeypatch.setattr(importer, "import_inboxes", fake_import(result, calls))
    assert run(make_config(tmp_path), "import") == 0
    out = capsys.readouterr().out
    assert out == (
        "moved nes 2\nmoved snes 1\n"
        "duplicates 1 (moved to <inbox>/duplicates)\n"
        "unmatched 2 (moved to <inbox>/unmatched)\n"
    )
    assert out.isascii()
    assert calls == [False]


def test_import_dry_run_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bool] = []
    result = importer.ImportResult({"nes": 2}, [], [Path("b")], [])
    monkeypatch.setattr(importer, "import_inboxes", fake_import(result, calls))
    assert run(make_config(tmp_path), "import", "--dry-run") == 0
    assert capsys.readouterr().out == (
        "would move nes 2\nunmatched 1 (would move to <inbox>/unmatched)\n"
    )
    assert calls == [True]


def test_import_empty_inbox(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = importer.ImportResult({}, [], [], [])
    monkeypatch.setattr(importer, "import_inboxes", fake_import(result, []))
    assert run(make_config(tmp_path), "import") == 0
    assert capsys.readouterr().out == "inbox is empty\n"


def test_import_hook_failure_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = importer.ImportResult({"nes": 1}, [], [], ["touch x: exit status 1"])
    monkeypatch.setattr(importer, "import_inboxes", fake_import(result, []))
    assert run(make_config(tmp_path), "import") == 1
    captured = capsys.readouterr()
    assert captured.out == "moved nes 1\n"
    assert captured.err == "rom-scraper: error: after_import hook failed: touch x: exit status 1\n"


def test_import_without_dat_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(make_config(tmp_path), "import") == 2
    assert "no DAT for nes" in capsys.readouterr().err
