from pathlib import Path

import pytest

from rom_scraper import __version__, cli


def make_config(tmp_path: Path, *, mkdirs: bool = True) -> Path:
    if mkdirs:
        (tmp_path / "roms").mkdir()
        (tmp_path / "inbox").mkdir()
    path = tmp_path / "config.toml"
    path.write_text(
        f'[library]\nroms = "{tmp_path / "roms"}"\ninboxes = ["{tmp_path / "inbox"}"]\n'
        '[platforms.nes]\ndat = "no-intro/Nintendo - Nintendo Entertainment System"\n'
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
    assert "nes: no-intro/Nintendo - Nintendo Entertainment System [USA, World]" in out
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
