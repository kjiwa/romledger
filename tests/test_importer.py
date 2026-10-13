from collections.abc import Sequence
from pathlib import Path

import pytest

from romledger import config, dats, igir, importer, scan

DAT_NAME = "Nintendo - Nintendo Entertainment System"
Row = igir.ReportRow


def row(status: str, game: str = "", path: Path | str = "") -> Row:
    return Row(DAT_NAME if game else "", status, game, str(path))


class Env:
    def __init__(self, tmp_path: Path, hooks: tuple[tuple[str, ...], ...] = ()) -> None:
        self.roms, self.inbox, self.data = tmp_path / "roms", tmp_path / "inbox", tmp_path / "data"
        self.roms.mkdir()
        self.inbox.mkdir()
        self.config = config.Config(
            config.Library(self.roms, (self.inbox,)),
            {"nes": config.Platform(f"no-intro/{DAT_NAME}")},
            config.Hooks(hooks),
        )
        path = dats.dat_path(self.data, f"no-intro/{DAT_NAME}")
        path.parent.mkdir(parents=True)
        path.write_text('clrmamepro (\n\tversion "1"\n)\n')
        self.reports: list[list[Row]] = []
        self.moves: list[tuple[list[Path], str, Sequence[str]]] = []
        self.hooks: list[Sequence[str]] = []
        self.hook_status = 0

    def report(
        self,
        dat_files: list[Path],
        inputs: Sequence[Path],
        cache: Path,
        filters: igir.Filters | None,
        excludes: Sequence[str],
    ) -> list[Row]:
        if filters is not None:
            return []
        assert excludes == (f"{self.inbox}/unmatched/**", f"{self.inbox}/duplicates/**")
        return self.reports.pop(0)

    def move(
        self,
        dat_files: list[Path],
        inputs: Sequence[Path],
        template: str,
        cache: Path,
        excludes: Sequence[str],
    ) -> None:
        self.moves.append((dat_files, template, excludes))

    def hook(self, argv: Sequence[str]) -> int:
        self.hooks.append(argv)
        if self.hook_status < 0:
            raise FileNotFoundError(argv[0])
        return self.hook_status

    def run(self, *, dry_run: bool = False) -> importer.ImportResult:
        return importer.import_inboxes(
            self.config, self.data, dry_run, self.report, self.move, self.hook
        )


def make_files(env: Env) -> dict[str, Path]:
    files = {"dup": env.inbox / "Alpha.nes", "mystery": env.inbox / "sub" / "Mystery.nes"}
    files["dup"].write_text("a")
    files["mystery"].parent.mkdir()
    files["mystery"].write_text("m")
    return files


def test_missing_dat(tmp_path: Path) -> None:
    env = Env(tmp_path)
    dats.dat_path(env.data, f"no-intro/{DAT_NAME}").unlink()
    with pytest.raises(config.ConfigError, match="no DAT for nes"):
        env.run()


def test_no_platforms_configured(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.config = config.Config(env.config.library, {}, env.config.hooks)
    with pytest.raises(config.ConfigError, match="no platforms configured"):
        env.run()


def test_empty_inbox(tmp_path: Path) -> None:
    env = Env(tmp_path, (("true",),))
    env.reports = [[row("MISSING", "A"), row("MISSING", "B")]]
    result = env.run()
    assert result == importer.ImportResult({}, [], [], [])
    assert env.moves == [] and env.hooks == []


def test_classifies_and_relocates(tmp_path: Path) -> None:
    env = Env(tmp_path, (("touch", "x"),))
    files = make_files(env)
    env.reports = [
        [
            row("FOUND", "A", files["dup"]),
            row("FOUND", "B", "/gone/B.nes"),
            row("MISSING", "C"),
            row("UNUSED", path=files["mystery"]),
        ],
        [row("FOUND", "A", files["dup"]), row("UNUSED", path=files["mystery"])],
    ]
    result = env.run()
    assert result.moved == {"nes": 1}
    assert result.duplicates == [env.inbox / "duplicates" / "Alpha.nes"]
    assert result.unmatched == [env.inbox / "unmatched" / "sub" / "Mystery.nes"]
    assert (env.inbox / "duplicates" / "Alpha.nes").read_text() == "a"
    assert (env.inbox / "unmatched" / "sub" / "Mystery.nes").read_text() == "m"
    assert not files["dup"].exists() and not files["mystery"].exists()
    assert env.moves == [
        (
            [dats.dat_path(env.data, f"no-intro/{DAT_NAME}")],
            f"{env.roms}/{{romm}}",
            (f"{env.inbox}/unmatched/**", f"{env.inbox}/duplicates/**"),
        )
    ]
    assert env.hooks == [("touch", "x")]
    assert result.hook_failures == []


def test_rescans_only_moved_platforms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = Env(tmp_path)
    rescanned: list[str] = []
    monkeypatch.setattr(scan, "scan_platform", lambda cfg, slug, data, rep: rescanned.append(slug))
    env.reports = [[row("FOUND", "A", "/gone/A")], []]
    env.run()
    assert rescanned == ["nes"]
    rescanned.clear()
    env.reports = [[row("UNUSED", path="/elsewhere/x")], [row("UNUSED", path="/elsewhere/x")]]
    env.run()
    assert rescanned == []


def test_second_dat_name_is_ignored(tmp_path: Path) -> None:
    env = Env(tmp_path)
    other = Row("Other - System", "FOUND", "Z", "/gone/Z")
    env.reports = [
        [other, row("UNUSED", path="/elsewhere/x")],
        [row("UNUSED", path="/elsewhere/x")],
    ]
    assert env.run().moved == {}


def test_moved_counts_files_that_left_the_inbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = Env(tmp_path)
    monkeypatch.setattr(scan, "scan_platform", lambda *args: None)
    stays = env.inbox / "A copy.nes"
    stays.write_text("a")
    env.reports = [
        [
            row("FOUND", "A", stays),
            row("FOUND", "A", "/g/filed.nes"),
            row("FOUND", "A", "/g/filed.nes"),
        ],
        [row("FOUND", "A", stays)],
    ]
    assert env.run().moved == {"nes": 1}


def test_path_outside_inbox_is_left_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = Env(tmp_path)
    outside = tmp_path / "elsewhere" / "x.nes"
    outside.parent.mkdir()
    outside.write_text("x")
    env.reports = [
        [row("UNUSED", path=outside)],
        [row("UNUSED", path=outside)],
    ]
    result = env.run()
    assert result.unmatched == []
    assert outside.read_text() == "x"
    assert f"warning: {outside} is not under any inbox" in capsys.readouterr().err


def test_collision_gets_numeric_suffix(tmp_path: Path) -> None:
    env = Env(tmp_path)
    taken = env.inbox / "unmatched" / "Mystery.nes"
    taken.parent.mkdir()
    taken.write_text("old")
    (env.inbox / "unmatched" / "Mystery.1.nes").write_text("old1")
    new = env.inbox / "Mystery.nes"
    new.write_text("new")
    env.reports = [[row("UNUSED", path=new)], [row("UNUSED", path=new)]]
    result = env.run()
    assert result.unmatched == [env.inbox / "unmatched" / "Mystery.2.nes"]
    assert taken.read_text() == "old"
    assert (env.inbox / "unmatched" / "Mystery.2.nes").read_text() == "new"


def test_dry_run_touches_nothing(tmp_path: Path) -> None:
    env = Env(tmp_path, (("true",),))
    files = make_files(env)
    env.reports = [
        [row("FOUND", "A", files["dup"]), row("UNUSED", path=files["mystery"])],
    ]
    result = env.run(dry_run=True)
    assert result.moved == {"nes": 1}
    assert result.unmatched == [files["mystery"]]
    assert result.duplicates == []
    assert files["dup"].exists() and files["mystery"].exists()
    assert not (env.inbox / "unmatched").exists()
    assert env.moves == [] and env.hooks == []


def test_hook_not_run_when_nothing_moved(tmp_path: Path) -> None:
    env = Env(tmp_path, (("true",),))
    env.reports = [[row("UNUSED", path="/elsewhere/x")], [row("UNUSED", path="/elsewhere/x")]]
    env.run()
    assert env.hooks == []


@pytest.mark.parametrize(("status", "expected"), [(3, "exit status 3"), (-1, "bad")])
def test_hook_failures_are_recorded(tmp_path: Path, status: int, expected: str) -> None:
    env = Env(tmp_path, (("bad", "arg"), ("good",)))
    env.hook_status = status
    env.reports = [[row("FOUND", "A", "/gone/A")], []]
    result = env.run()
    assert env.hooks == [("bad", "arg"), ("good",)]
    assert len(result.hook_failures) == 2
    assert result.hook_failures[0].startswith("bad arg: ")
    assert expected in result.hook_failures[0]


def test_run_hook_returns_status() -> None:
    assert importer.run_hook(["true"]) == 0
    assert importer.run_hook(["false"]) == 1
