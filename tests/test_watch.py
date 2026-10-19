from pathlib import Path

import pytest

from romledger import config, watch
from romledger.context import Context


def context(tmp_path: Path) -> Context:
    inbox = tmp_path / "inbox"
    inbox.mkdir(exist_ok=True)
    cfg = config.Config(config.Library(tmp_path / "roms", (inbox,)), {})
    return Context(tmp_path / "config.toml", cfg, {}, tmp_path / "data")


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.inbox = tmp_path / "inbox"
        self.imports: list[Context] = []
        self.warnings: list[str] = []
        self.failure: Exception | None = None
        self.load_failure: Exception | None = None
        self.leave: bool = False
        self.watcher = watch.Watcher(self.load, self.run_import, self.warnings.append)

    def load(self) -> Context:
        if self.load_failure:
            raise self.load_failure
        return context(self.tmp_path)

    def run_import(self, loaded: Context) -> None:
        self.imports.append(loaded)
        if self.failure:
            raise self.failure
        if not self.leave:
            for path in self.inbox.iterdir():
                if path.is_file():
                    path.unlink()

    def put(self, name: str, content: bytes = b"x") -> Path:
        self.inbox.mkdir(exist_ok=True)
        path = self.inbox / name
        path.write_bytes(content)
        return path

    def settle(self) -> bool:
        started = False
        for _ in range(watch.STEADY_POLLS + 1):
            started = self.watcher.poll() or started
        return started


def test_snapshot_skips_junk_set_aside_folders_and_partial_files(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    (inbox / "sub").mkdir(parents=True)
    (inbox / "unmatched").mkdir()
    (inbox / "sub" / "keep.nes").write_bytes(b"1")
    (inbox / "unmatched" / "old.nes").write_bytes(b"1")
    (inbox / ".DS_Store").write_bytes(b"1")
    (inbox / "._a.nes").write_bytes(b"1")
    (inbox / "b.part").write_bytes(b"1")
    assert list(watch.snapshot([inbox])) == [str(inbox / "sub" / "keep.nes")]


def test_snapshot_keeps_set_aside_names_below_the_top(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    (inbox / "sub" / "unmatched").mkdir(parents=True)
    (inbox / "sub" / "unmatched" / "x.nes").write_bytes(b"1")
    assert len(watch.snapshot([inbox])) == 1


def test_snapshot_ignores_a_file_that_vanishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.nes").write_bytes(b"1")
    real = Path.stat

    def flaky(self: Path, **kwargs: bool) -> object:
        if self.name == "a.nes":
            raise FileNotFoundError
        return real(self, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky)
    assert watch.snapshot([inbox]) == {}


def test_a_file_is_imported_once_it_stops_changing(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.put("a.nes")
    assert harness.watcher.poll() is False
    assert harness.watcher.poll() is False
    assert harness.watcher.poll() is True
    assert len(harness.imports) == 1


def test_a_file_that_keeps_growing_is_left_alone(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    for size in range(1, 6):
        harness.put("a.nes", b"x" * size)
        assert harness.watcher.poll() is False
    assert harness.imports == []


def test_an_empty_inbox_does_nothing(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    assert harness.settle() is False
    assert harness.imports == []


def test_files_the_import_leaves_behind_are_not_retried_until_they_change(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.leave = True
    path = harness.put("a.nes")
    assert harness.settle() is True
    assert harness.settle() is False
    assert len(harness.imports) == 1
    path.write_bytes(b"changed")
    assert harness.settle() is True
    assert len(harness.imports) == 2


def test_a_file_that_arrives_during_an_import_is_picked_up_next(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.put("a.nes")

    def run_import(loaded: Context) -> None:
        harness.imports.append(loaded)
        harness.put("late.nes")

    harness.watcher = watch.Watcher(harness.load, run_import, harness.warnings.append)
    assert harness.settle() is True
    assert harness.settle() is True
    assert len(harness.imports) == 2


def test_the_attempt_is_forgotten_when_the_inbox_empties(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.leave = True
    path = harness.put("a.nes")
    harness.settle()
    path.unlink()
    harness.settle()
    harness.put("a.nes")
    assert harness.settle() is True
    assert len(harness.imports) == 2


def test_a_failed_import_warns_once_and_is_not_retried_in_a_loop(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.failure = config.ConfigError("no DAT could be downloaded")
    harness.put("a.nes")
    assert harness.settle() is False
    assert harness.settle() is False
    assert harness.warnings == ["no DAT could be downloaded"]
    assert len(harness.imports) == 1


def test_a_library_that_is_not_mounted_warns_once_then_recovers(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.load_failure = config.ConfigError("roms: not a directory")
    assert harness.watcher.poll() is False
    assert harness.watcher.poll() is False
    assert harness.warnings == ["roms: not a directory"]
    harness.load_failure = None
    harness.put("a.nes")
    assert harness.settle() is True
    harness.load_failure = config.ConfigError("roms: not a directory")
    harness.watcher.poll()
    assert harness.warnings == ["roms: not a directory", "roms: not a directory"]


def test_run_polls_after_each_pause(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    sleeps: list[float] = []

    class Stop(Exception):
        pass

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == watch.STEADY_POLLS + 2:
            raise Stop

    watcher = watch.Watcher(harness.load, harness.run_import, harness.warnings.append, 2.5, sleep)
    harness.put("a.nes")
    with pytest.raises(Stop):
        watcher.run()
    assert sleeps == [2.5] * (watch.STEADY_POLLS + 2)
    assert len(harness.imports) == 1
