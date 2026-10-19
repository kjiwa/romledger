import io
import os
import sys
import tempfile
from pathlib import Path

import pytest

from romledger import cli, config, registry


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
    assert init(tmp_path, "--roms", str(roms)) == 0
    assert (roms / "library").is_dir()
    assert (roms / "inbox").is_dir()
    loaded = config.load(tmp_path / "c.toml", registry.load())
    assert loaded.library.roms == roms / "library"
    assert loaded.library.inboxes == (roms / "inbox",)
    out = capsys.readouterr().out
    assert out.isascii()
    assert f"wrote {tmp_path / 'c.toml'}" in out
    assert f"Put ROMs in {roms / 'inbox'}, then:" in out
    for command in ("romledger import", "romledger status"):
        assert command in out


def test_init_keeps_existing_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stdin(monkeypatch, None)
    (tmp_path / "roms" / "library" / "nes").mkdir(parents=True)
    (tmp_path / "roms" / "inbox").mkdir()
    (tmp_path / "roms" / "inbox" / "a.nes").write_text("x")
    assert init(tmp_path, "--roms", str(tmp_path / "roms")) == 0
    assert (tmp_path / "roms" / "inbox" / "a.nes").read_text() == "x"


def test_init_defaults_roms_to_home(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdin(monkeypatch, None)
    assert init(tmp_path) == 0
    assert (home / "roms" / "library").is_dir()


def test_init_refuses_to_overwrite(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "c.toml").write_text("keep")
    assert init(tmp_path, "--roms", str(tmp_path / "roms")) == 2
    err = capsys.readouterr().err
    assert "already exists" in err
    assert "--force" in err
    assert (tmp_path / "c.toml").read_text() == "keep"
    assert not (tmp_path / "roms").exists()


def test_init_force_overwrites(tmp_path: Path) -> None:
    (tmp_path / "c.toml").write_text("keep")
    assert init(tmp_path, "--roms", str(tmp_path / "roms"), "--force") == 0
    assert (tmp_path / "c.toml").read_text().startswith("[library]")


def test_init_writes_only_the_library_and_commented_hints(tmp_path: Path) -> None:
    assert init(tmp_path, "--roms", str(tmp_path / "roms")) == 0
    lines = (tmp_path / "c.toml").read_text().splitlines()
    assert [line for line in lines if line.startswith("[")] == ["[library]"]
    assert "# [wanted]" in lines
    assert "# [platforms.snes]" in lines


def test_init_interactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    roms = tmp_path / "roms"
    stdin(monkeypatch, f"{roms}\ny\n")
    assert init(tmp_path) == 0
    assert capsys.readouterr().out.isascii()
    loaded = config.load(tmp_path / "c.toml", registry.load())
    extra = tmp_path / "home" / "Downloads" / "romledger"
    assert loaded.library.inboxes == (roms / "inbox", extra)
    assert extra.is_dir()


def test_init_interactive_defaults(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdin(monkeypatch, "\n\n")
    assert init(tmp_path) == 0
    loaded = config.load(tmp_path / "c.toml", registry.load())
    assert loaded.library.roms == home / "roms" / "library"
    assert len(loaded.library.inboxes) == 1
    assert not (home / "Downloads").exists()


def test_init_interactive_skips_answered_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdin(monkeypatch, "n\n")
    assert init(tmp_path, "--roms", str(tmp_path / "roms")) == 0
    assert not (tmp_path / "home" / "Downloads").exists()


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
    argv = ["--config", str(path), "init", "--roms", str(tmp_path / "r")]
    assert cli.main(argv) == 0
    assert path.is_file()


def test_init_names_config_flag_for_other_locations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stdin(monkeypatch, None)
    init(tmp_path, "--roms", str(tmp_path / "r"))
    assert "--config" in capsys.readouterr().out


def test_init_default_location_needs_no_config_note(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stdin(monkeypatch, None)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert cli.main(["init", "--roms", str(tmp_path / "r")]) == 0
    assert (home / ".config" / "romledger" / "config.toml").is_file()
    assert "--config" not in capsys.readouterr().out


def test_init_roms_is_a_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "roms").write_text("x")
    assert init(tmp_path, "--roms", str(tmp_path / "roms")) == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert f"{tmp_path / 'roms'}: not a directory" in err
    assert not (tmp_path / "c.toml").exists()


def test_init_config_path_is_a_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "c.toml").mkdir()
    assert init(tmp_path, "--roms", str(tmp_path / "r"), "--force") == 2
    assert "is a directory" in capsys.readouterr().err
    assert not (tmp_path / "r").exists()


def test_init_parent_is_a_file(tmp_path: Path) -> None:
    (tmp_path / "blocker").write_text("x")
    assert init(tmp_path, "--roms", str(tmp_path / "blocker" / "r")) == 2
    assert not (tmp_path / "c.toml").exists()


def test_init_unwritable_parent_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(os, "access", lambda *_: False)
    assert init(tmp_path, "--roms", str(tmp_path / "r")) == 2
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
    args = ("--roms", str(tmp_path / "r"), "--force")
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
    assert init(tmp_path, "--roms", str(tmp_path / "r")) == 2
    assert not (tmp_path / "c.toml").exists()
    assert not (tmp_path / ".romledger-x").exists()


@pytest.mark.parametrize(
    ("error", "code"), [(KeyboardInterrupt, 130), (EOFError, 2)], ids=["ctrl-c", "eof"]
)
@pytest.mark.parametrize("after", [0, 1])
def test_init_prompt_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: type[BaseException],
    code: int,
    after: int,
) -> None:
    stdin(monkeypatch, "")
    answers = iter([str(tmp_path / "r")][:after])

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
