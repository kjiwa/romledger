import io
import os
import sys
import tempfile
from pathlib import Path

import pytest

from romledger import cli, config, registry, setup


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    monkeypatch.delenv(config.CONFIG_ENV, raising=False)
    return path


def stdin(monkeypatch: pytest.MonkeyPatch, text: str | None) -> None:
    stream = io.StringIO(text or "")
    monkeypatch.setattr(stream, "isatty", lambda: text is not None)
    monkeypatch.setattr(sys, "stdin", stream)


def init(tmp_path: Path, *args: str) -> int:
    return cli.main(["--config", str(tmp_path / "c.toml"), "init", *args])


def test_init_with_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stdin(monkeypatch, None)
    roms = tmp_path / "roms"
    assert init(tmp_path, "--roms", str(roms), "--platform", "nes", "--platform", "snes") == 0
    assert (roms / "library").is_dir()
    assert (roms / "inbox").is_dir()
    loaded = config.load(tmp_path / "c.toml", registry.load())
    assert list(loaded.platforms) == ["nes", "snes"]
    assert loaded.library.roms == roms / "library"
    assert loaded.library.inboxes == (roms / "inbox",)
    out = capsys.readouterr().out
    assert out.isascii()
    assert f"wrote {tmp_path / 'c.toml'}" in out
    for command in ("romledger dats update", "romledger scan", "romledger serve --open"):
        assert command in out


def test_init_keeps_existing_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stdin(monkeypatch, None)
    (tmp_path / "roms" / "library" / "nes").mkdir(parents=True)
    (tmp_path / "roms" / "inbox").mkdir()
    (tmp_path / "roms" / "inbox" / "a.nes").write_text("x")
    assert init(tmp_path, "--roms", str(tmp_path / "roms"), "--platform", "nes") == 0
    assert (tmp_path / "roms" / "inbox" / "a.nes").read_text() == "x"


def test_init_defaults_roms_to_home(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdin(monkeypatch, None)
    assert init(tmp_path, "--platform", "nes") == 0
    assert (home / "roms" / "library").is_dir()


def test_init_refuses_to_overwrite(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "c.toml").write_text("keep")
    assert init(tmp_path, "--roms", str(tmp_path / "roms"), "--platform", "nes") == 2
    err = capsys.readouterr().err
    assert "already exists" in err
    assert "--force" in err
    assert (tmp_path / "c.toml").read_text() == "keep"
    assert not (tmp_path / "roms").exists()


def test_init_force_overwrites(tmp_path: Path) -> None:
    (tmp_path / "c.toml").write_text("keep")
    args = ("--roms", str(tmp_path / "roms"), "--platform", "nes", "--force")
    assert init(tmp_path, *args) == 0
    assert "[platforms.nes]" in (tmp_path / "c.toml").read_text()


def test_init_without_platform_needs_a_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stdin(monkeypatch, None)
    assert init(tmp_path, "--roms", str(tmp_path / "roms")) == 2
    err = capsys.readouterr().err
    assert "usage: romledger init" in err
    assert not (tmp_path / "c.toml").exists()


def test_init_rejects_unknown_platform_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert init(tmp_path, "--roms", str(tmp_path / "r"), "--platform", "nez") == 2
    err = capsys.readouterr().err
    assert "unknown platform 'nez'" in err
    assert "nes" in err
    assert not (tmp_path / "r").exists()


def test_init_unknown_platform_without_near_match() -> None:
    message = setup.unknown_message(["zzzzzzzz"], registry.load())
    assert message is not None
    assert "romledger platforms" in message


def test_init_interactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    roms = tmp_path / "roms"
    stdin(monkeypatch, f"{roms}\n\nnez snes\nnes, snes\ny\n")
    assert init(tmp_path) == 0
    out = capsys.readouterr().out
    assert "unknown platform 'nez'" in out
    assert "Nearest: nes" in out
    assert "no-intro/Nintendo - Nintendo Entertainment System" in out
    assert out.isascii()
    loaded = config.load(tmp_path / "c.toml", registry.load())
    assert list(loaded.platforms) == ["nes", "snes"]
    extra = tmp_path / "home" / "Downloads" / "romledger"
    assert loaded.library.inboxes == (roms / "inbox", extra)
    assert extra.is_dir()


def test_init_interactive_defaults(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdin(monkeypatch, "\nnes\n\n")
    assert init(tmp_path) == 0
    loaded = config.load(tmp_path / "c.toml", registry.load())
    assert loaded.library.roms == home / "roms" / "library"
    assert len(loaded.library.inboxes) == 1
    assert not (home / "Downloads").exists()


def test_init_interactive_skips_answered_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdin(monkeypatch, "n\n")
    assert init(tmp_path, "--roms", str(tmp_path / "roms"), "--platform", "nes") == 0


def test_init_input_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stdin(monkeypatch, "")
    assert init(tmp_path) == 2
    assert capsys.readouterr().err.endswith("romledger: error: cancelled\n")
    assert not (tmp_path / "c.toml").exists()


def test_init_creates_config_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stdin(monkeypatch, None)
    path = tmp_path / "deep" / "dir" / "c.toml"
    argv = ["--config", str(path), "init", "--roms", str(tmp_path / "r"), "--platform", "nes"]
    assert cli.main(argv) == 0
    assert path.is_file()


def test_init_names_config_flag_for_other_locations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stdin(monkeypatch, None)
    init(tmp_path, "--roms", str(tmp_path / "r"), "--platform", "nes")
    assert "--config" in capsys.readouterr().out


def test_init_default_location_needs_no_config_note(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stdin(monkeypatch, None)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert cli.main(["init", "--roms", str(tmp_path / "r"), "--platform", "nes"]) == 0
    assert (home / ".config" / "romledger" / "config.toml").is_file()
    assert "--config" not in capsys.readouterr().out


def test_platforms_lines_wrap() -> None:
    lines = setup.platform_lines(registry.load(), {"nes"})
    assert all(len(line) <= setup.WIDTH for line in lines)
    assert all(line.isascii() for line in lines)
    nes = next(i for i, line in enumerate(lines) if line.startswith("nes  "))
    assert lines[nes].startswith("nes  no-intro/Nintendo - Nintendo")
    assert "[configured]" in "".join(lines[nes : nes + 3])
    assert sum(not line.startswith(" ") for line in lines) == len(registry.load())


def test_platforms_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "c.toml"
    (tmp_path / "roms").mkdir()
    (tmp_path / "inbox").mkdir()
    path.write_text(
        f'[library]\nroms = "{tmp_path / "roms"}"\ninboxes = ["{tmp_path / "inbox"}"]\n'
        "[platforms.snes]\n"
    )
    assert cli.main(["--config", str(path), "platforms"]) == 0
    out = capsys.readouterr().out
    assert out.count("[configured]") == 1
    assert out.splitlines()[0].startswith("atari")
    assert max(len(line) for line in out.splitlines()) <= setup.WIDTH


def test_platforms_command_without_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--config", str(tmp_path / "none.toml"), "platforms"]) == 0
    assert "[configured]" not in capsys.readouterr().out


def test_init_deduplicates_platform_flags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stdin(monkeypatch, None)
    args = ("--roms", str(tmp_path / "r"), "--platform", "snes", "--platform", "nes")
    assert init(tmp_path, *args, "--platform", "snes") == 0
    loaded = config.load(tmp_path / "c.toml", registry.load())
    assert list(loaded.platforms) == ["snes", "nes"]


def test_init_duplicate_unknown_still_errors(tmp_path: Path) -> None:
    args = ("--platform", "nes", "--platform", "nez", "--platform", "nez")
    assert init(tmp_path, "--roms", str(tmp_path / "r"), *args) == 2
    assert not (tmp_path / "r").exists()


def test_init_roms_is_a_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "roms").write_text("x")
    assert init(tmp_path, "--roms", str(tmp_path / "roms"), "--platform", "nes") == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert f"{tmp_path / 'roms'}: not a directory" in err
    assert not (tmp_path / "c.toml").exists()


def test_init_config_path_is_a_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "c.toml").mkdir()
    assert init(tmp_path, "--roms", str(tmp_path / "r"), "--platform", "nes", "--force") == 2
    assert "is a directory" in capsys.readouterr().err
    assert not (tmp_path / "r").exists()


def test_init_parent_is_a_file(tmp_path: Path) -> None:
    (tmp_path / "blocker").write_text("x")
    assert init(tmp_path, "--roms", str(tmp_path / "blocker" / "r"), "--platform", "nes") == 2
    assert not (tmp_path / "c.toml").exists()


def test_init_unwritable_parent_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(os, "access", lambda *_: False)
    assert init(tmp_path, "--roms", str(tmp_path / "r"), "--platform", "nes") == 2
    assert "Check its permissions" in capsys.readouterr().err
    assert not (tmp_path / "r").exists()
    assert not (tmp_path / "c.toml").exists()


def test_init_force_keeps_old_config_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "c.toml").write_text("keep")

    def fail(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    args = ("--roms", str(tmp_path / "r"), "--platform", "nes", "--force")
    assert init(tmp_path, *args) == 2
    assert (tmp_path / "c.toml").read_text() == "keep"
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".romledger-")] == []


def test_init_write_failure_removes_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Broken:
        def __init__(self, *_: object, **kwargs: object) -> None:
            self.name = str(Path(str(kwargs["dir"])) / ".romledger-x")
            Path(self.name).write_text("")

        def __enter__(self) -> "Broken":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def write(self, _: str) -> None:
            raise OSError("disk full")

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", Broken)
    assert init(tmp_path, "--roms", str(tmp_path / "r"), "--platform", "nes") == 2
    assert not (tmp_path / "c.toml").exists()
    assert not (tmp_path / ".romledger-x").exists()


@pytest.mark.parametrize(
    ("error", "code"), [(KeyboardInterrupt, 130), (EOFError, 2)], ids=["ctrl-c", "eof"]
)
@pytest.mark.parametrize("after", [0, 1, 2])
def test_init_prompt_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: type[BaseException],
    code: int,
    after: int,
) -> None:
    stdin(monkeypatch, "")
    answers = iter([str(tmp_path / "r"), "nes"][:after])

    def fake_input(_: str) -> str:
        try:
            return next(answers)
        except StopIteration:
            raise error from None

    monkeypatch.setattr("builtins.input", fake_input)
    assert init(tmp_path) == code
    assert capsys.readouterr().err.endswith("\nromledger: error: cancelled\n")
    assert not (tmp_path / "c.toml").exists()
    assert not (tmp_path / "r").exists()


def test_platforms_warns_on_invalid_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "c.toml").write_text("[library\n")
    assert cli.main(["--config", str(tmp_path / "c.toml"), "platforms"]) == 0
    captured = capsys.readouterr()
    assert captured.err.startswith("romledger: warning: ")
    assert captured.err.count("\n") == 1
    assert len(captured.out.splitlines()) >= len(registry.load())
