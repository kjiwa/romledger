import shutil
from collections.abc import Sequence
from pathlib import Path
from xml.etree import ElementTree

import pytest

from romledger import config, dats, igir, importer, scan

DAT_NAME = "Nintendo - Nintendo Entertainment System"
GAMES = ["Alpha (USA)", "Alpha (USA) (Rev 1)", "Beta (USA) (Unl)", "Gamma (Japan)", "Delta (World)"]
DAT = f'clrmamepro (\n\tname "{DAT_NAME}"\n\tversion "1"\n)\n' + "".join(
    f'game (\n\tname "{name}"\n\trom ( name "{name}.nes" size 1 sha1 {str(i) * 40} )\n)\n'
    for i, name in enumerate(GAMES)
)
Row = igir.ReportRow


def row(status: str, game: str = "", path: Path | str = "") -> Row:
    return Row(DAT_NAME if game else "", status, game, str(path))


@pytest.fixture(autouse=True)
def no_rescan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scan, "scan_platform", lambda *args: None)


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
        path.write_text(DAT)
        self.full_dat = path
        self.reports: list[list[Row]] = []
        self.library_reports: list[list[Row]] = []
        self.report_dats: list[list[Path]] = []
        self.subsets: list[str] = []
        self.moves: list[tuple[str, Sequence[str]]] = []
        self.deletes_emptied_inbox = False
        self.move_error: Exception | None = None
        self.hooks: list[Sequence[str]] = []
        self.hook_status = 0

    def report(
        self,
        dat_files: list[Path],
        inputs: Sequence[Path],
        cache: Path,
        excludes: Sequence[str],
    ) -> list[Row]:
        if list(inputs) == [self.roms]:
            return self.library_reports.pop(0) if self.library_reports else []
        assert excludes == igir.inbox_excludes([self.inbox])
        self.report_dats.append(list(dat_files))
        return self.reports.pop(0)

    def move(
        self,
        dat_files: list[Path],
        inputs: Sequence[Path],
        template: str,
        cache: Path,
        excludes: Sequence[str],
    ) -> None:
        self.subsets.extend(path.read_text() for path in dat_files)
        self.moves.append((template, excludes))
        if self.deletes_emptied_inbox:
            shutil.rmtree(self.inbox)
        if self.move_error:
            raise self.move_error

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
    files = {
        "dup": env.inbox / "Alpha.nes",
        "mystery": env.inbox / "sub" / "Mystery.nes",
        "japan": env.inbox / "Gamma.nes",
    }
    files["mystery"].parent.mkdir()
    for name, path in files.items():
        path.write_text(name)
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
    assert result == importer.ImportResult({}, [], [], [], [])
    assert env.moves == [] and env.hooks == []


def test_classifies_and_relocates(tmp_path: Path) -> None:
    env = Env(tmp_path, (("touch", "x"),))
    files = make_files(env)
    env.reports = [
        [
            row("FOUND", "Alpha (USA)", files["dup"]),
            row("FOUND", "Delta (World)", "/gone/D.nes"),
            row("MISSING", "Alpha (USA) (Rev 1)"),
            row("UNUSED", path=files["mystery"]),
            row("UNUSED", path=files["japan"]),
        ],
        [row("FOUND", "Alpha (USA)", files["dup"]), row("UNUSED", path=files["mystery"])],
        [row("FOUND", "Gamma (Japan)", files["japan"]), row("UNUSED", path=files["mystery"])],
    ]
    env.library_reports = [[row("FOUND", "Alpha (USA)", "/g/A.nes")]] * 2
    result = env.run()
    assert result.moved == {"nes": 1}
    assert result.duplicates == [env.inbox / "duplicates" / "Alpha.nes"]
    assert result.unwanted == [env.inbox / "unwanted" / "Gamma.nes"]
    assert result.unmatched == [env.inbox / "unmatched" / "sub" / "Mystery.nes"]
    assert (env.inbox / "duplicates" / "Alpha.nes").read_text() == "dup"
    assert (env.inbox / "unwanted" / "Gamma.nes").read_text() == "japan"
    assert (env.inbox / "unmatched" / "sub" / "Mystery.nes").read_text() == "mystery"
    assert [path.exists() for path in files.values()] == [False] * 3
    assert env.moves == [(f"{env.roms}/{{romm}}", igir.inbox_excludes([env.inbox]))]
    assert env.hooks == [("touch", "x")]
    assert result.hook_failures == []


def test_moves_only_wanted_groups_and_splits_leftovers_by_the_full_dat(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.reports = [[row("UNUSED", path="/elsewhere/x")], [], [row("UNUSED", path="/elsewhere/x")]]
    env.run()
    assert len(env.subsets) == 1
    subset = ElementTree.fromstring(env.subsets[0])  # noqa: S314
    assert subset.findtext("header/name") == DAT_NAME
    assert [game.get("name") for game in subset.findall("game")] == [
        "Alpha (USA)",
        "Alpha (USA) (Rev 1)",
        "Delta (World)",
    ]
    assert env.report_dats[0] == env.report_dats[1] != [env.full_dat]
    assert env.report_dats[2] == [env.full_dat]


def test_subset_is_built_from_include(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.config = config.Config(
        env.config.library,
        {"nes": config.Platform(f"no-intro/{DAT_NAME}", include=("unlicensed",))},
    )
    env.reports = [[row("FOUND", "A", "/gone/A")], []]
    env.run()
    names = [game.get("name") for game in ElementTree.fromstring(env.subsets[0]).findall("game")]  # noqa: S314
    assert "Beta (USA) (Unl)" in names


def test_leftover_report_is_skipped_when_every_file_matched(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.reports = [[row("FOUND", "Alpha (USA)", "/gone/A")], []]
    env.run()
    assert len(env.report_dats) == 2


def test_rescans_only_moved_platforms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = Env(tmp_path)
    rescanned: list[str] = []
    monkeypatch.setattr(scan, "scan_platform", lambda cfg, slug, data, rep: rescanned.append(slug))
    env.reports = [[row("FOUND", "A", "/gone/A")], []]
    env.run()
    assert rescanned == ["nes"]
    rescanned.clear()
    env.reports = [[row("UNUSED", path="/elsewhere/x")], [], [row("UNUSED", path="/elsewhere/x")]]
    env.run()
    assert rescanned == []


def test_second_dat_name_is_ignored(tmp_path: Path) -> None:
    env = Env(tmp_path)
    other = Row("Other - System", "FOUND", "Z", "/gone/Z")
    env.reports = [
        [other, row("UNUSED", path="/elsewhere/x")],
        [],
        [row("UNUSED", path="/elsewhere/x")],
    ]
    assert env.run().moved == {}


def test_moved_counts_files_that_left_the_inbox(tmp_path: Path) -> None:
    env = Env(tmp_path)
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


def test_archive_kept_by_igir_is_extracted_and_counted_as_moved(tmp_path: Path) -> None:
    env = Env(tmp_path)
    zipped = env.inbox / "Alpha.zip"
    zipped.write_text("zip")
    env.reports = [[row("FOUND", "Alpha (USA)", zipped)], [row("FOUND", "Alpha (USA)", zipped)]]
    env.library_reports = [[], [row("FOUND", "Alpha (USA)", "/g/A.nes")]]
    result = env.run()
    assert result.moved == {"nes": 1}
    assert result.extracted == [env.inbox / "extracted" / "Alpha.zip"]
    assert result.duplicates == []
    assert not zipped.exists()


def test_file_igir_did_not_import_stays_put(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = Env(tmp_path)
    stuck = env.inbox / "Alpha.zip"
    stuck.write_text("zip")
    env.reports = [[row("FOUND", "Alpha (USA)", stuck)], [row("FOUND", "Alpha (USA)", stuck)]]
    result = env.run()
    assert result.moved == {} and result.extracted == [] and result.duplicates == []
    assert stuck.exists()
    assert f"warning: {stuck} was not imported" in capsys.readouterr().err


def test_library_report_is_skipped_before_the_library_exists(tmp_path: Path) -> None:
    env = Env(tmp_path)
    shutil.rmtree(env.roms)
    env.library_reports = [[row("FOUND", "Alpha (USA)", "/g/A.nes")]]
    env.reports = [[row("FOUND", "Alpha (USA)", "/gone/A")], []]
    assert env.run().moved == {"nes": 1}
    assert len(env.library_reports) == 1


def test_path_outside_inbox_is_left_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = Env(tmp_path)
    outside = tmp_path / "elsewhere" / "x.nes"
    outside.parent.mkdir()
    outside.write_text("x")
    env.reports = [[row("UNUSED", path=outside)], [], [row("UNUSED", path=outside)]]
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
    env.reports = [[row("UNUSED", path=new)], [], [row("UNUSED", path=new)]]
    result = env.run()
    assert result.unmatched == [env.inbox / "unmatched" / "Mystery.2.nes"]
    assert taken.read_text() == "old"
    assert (env.inbox / "unmatched" / "Mystery.2.nes").read_text() == "new"


def test_dry_run_touches_nothing(tmp_path: Path) -> None:
    env = Env(tmp_path, (("true",),))
    files = make_files(env)
    env.reports = [
        [
            row("FOUND", "Alpha (USA)", files["dup"]),
            row("UNUSED", path=files["mystery"]),
            row("UNUSED", path=files["japan"]),
        ],
        [
            row("FOUND", "Alpha (USA)", files["dup"]),
            row("FOUND", "Gamma (Japan)", files["japan"]),
            row("UNUSED", path=files["mystery"]),
        ],
    ]
    result = env.run(dry_run=True)
    assert result.moved == {"nes": 1}
    assert result.unwanted == [files["japan"]]
    assert result.unmatched == [files["mystery"]]
    assert result.duplicates == []
    assert all(path.exists() for path in files.values())
    assert not (env.inbox / "unmatched").exists() and not (env.inbox / "unwanted").exists()
    assert env.moves == [] and env.hooks == []


def test_hook_not_run_when_nothing_moved(tmp_path: Path) -> None:
    env = Env(tmp_path, (("true",),))
    env.reports = [[row("UNUSED", path="/elsewhere/x")], [], [row("UNUSED", path="/elsewhere/x")]]
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


def test_inbox_is_restored_when_igir_fails(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.deletes_emptied_inbox = True
    env.move_error = igir.ToolError("boom")
    env.reports = [[row("FOUND", "A", "/gone/A")]]
    with pytest.raises(igir.ToolError):
        env.run()
    assert env.inbox.is_dir()


def test_inbox_survives_igir_deleting_it(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.deletes_emptied_inbox = True
    env.reports = [[row("FOUND", "A", "/gone/A")], []]
    env.run()
    assert env.inbox.is_dir()
