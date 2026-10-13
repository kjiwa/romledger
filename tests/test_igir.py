import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from rom_scraper import igir

REPORT = (
    "DAT Name,Game Name,Status,ROM Files,Patched,BIOS,Retail Release\n"
    "Nintendo,Alpha (USA),FOUND,/roms/nes/Alpha (USA).nes,false,false,true\n"
    'Nintendo,"Beta, The (USA)",FOUND,"/roms/nes/Beta, The (USA).nes",false,false,true\n'
    "Nintendo,Gamma (USA),MISSING,,false,false,true\n"
    ",,UNUSED,/roms/nes/Mystery.nes,,,\n"
)


def fake_which(found: set[str]) -> Any:
    return lambda name: f"/bin/{name}" if name in found else None


def test_command_prefers_igir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", fake_which({"igir", "npx", "node"}))
    assert igir.command() == ["igir"]


def test_command_falls_back_to_npx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", fake_which({"npx", "node"}))
    assert igir.command() == ["npx", "--yes", f"igir@{igir.IGIR_VERSION}"]


@pytest.mark.parametrize("found", [set(), {"npx"}, {"node"}])
def test_command_requires_node(monkeypatch: pytest.MonkeyPatch, found: set[str]) -> None:
    monkeypatch.setattr(shutil, "which", fake_which(found))
    with pytest.raises(igir.ToolError, match=r"Node\.js 22\.22\+"):
        igir.command()


class Recorder:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.argv: list[str] = []
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.argv = argv
        if self.returncode == 0 and "--report-output" in argv:
            Path(argv[argv.index("--report-output") + 1]).write_text(REPORT)
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


def run_report(
    tmp_path: Path, runner: Recorder, filters: igir.Filters | None = None
) -> list[igir.ReportRow]:
    return igir.report(
        [Path("/data/a.dat"), Path("/data/b.dat")],
        [Path("/in/a"), Path("/in/b")],
        tmp_path / "cache" / "igir.cache",
        filters,
        ["/in/a/unmatched/**"],
        runner,
    )


def excludes_argv() -> list[str]:
    return [
        *(
            arg
            for directory in ("/in/a", "/in/b")
            for junk in igir.JUNK_EXCLUDES
            for arg in ("--input-exclude", f"{directory}/{junk}")
        ),
        *["--input-exclude", "/in/a/unmatched/**"],
    ]


def test_argv_and_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", fake_which({"igir"}))
    runner = Recorder()
    rows = run_report(tmp_path, runner, igir.Filters(("USA", "WORLD"), ("EN",)))
    output = runner.argv[runner.argv.index("--report-output") + 1]
    assert runner.argv == [
        *["igir", "report", "--dat", "/data/a.dat", "--dat", "/data/b.dat"],
        *["--input", "/in/a", "--input", "/in/b"],
        *excludes_argv(),
        *["--cache-path", str(tmp_path / "cache" / "igir.cache")],
        *["--single", "--filter-region", "USA,WORLD", "--filter-language", "EN"],
        *["--prefer-region", "USA,WORLD", "--prefer-language", "EN"],
        *["--report-output", output],
    ]
    assert rows == [
        igir.ReportRow("Nintendo", "FOUND", "Alpha (USA)", "/roms/nes/Alpha (USA).nes"),
        igir.ReportRow("Nintendo", "FOUND", "Beta, The (USA)", "/roms/nes/Beta, The (USA).nes"),
        igir.ReportRow("Nintendo", "MISSING", "Gamma (USA)", ""),
        igir.ReportRow("", "UNUSED", "", "/roms/nes/Mystery.nes"),
    ]


def test_report_without_filters_omits_selection_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", fake_which({"igir"}))
    runner = Recorder()
    run_report(tmp_path, runner)
    assert not {"--single", "--filter-region", "--prefer-region"} & set(runner.argv)


def test_move_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", fake_which({"igir"}))
    runner = Recorder()
    cache = tmp_path / "cache" / "igir.cache"
    igir.move(
        [Path("/data/a.dat")],
        [Path("/in/a")],
        "/roms/{romm}",
        cache,
        ["/in/a/unmatched/**"],
        runner,
    )
    assert runner.argv == [
        *["igir", "move", "--dat", "/data/a.dat", "--input", "/in/a"],
        *(arg for junk in igir.JUNK_EXCLUDES for arg in ("--input-exclude", f"/in/a/{junk}")),
        *["--input-exclude", "/in/a/unmatched/**"],
        *["--cache-path", str(cache), "--output", "/roms/{romm}"],
    ]


def test_move_failure_and_unrunnable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", fake_which({"igir"}))
    with pytest.raises(igir.ToolError, match="status 1"):
        igir.move([], [], "x", tmp_path / "c", (), Recorder(returncode=1, stderr="boom"))

    def broken(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise PermissionError("denied")

    with pytest.raises(igir.ToolError, match="cannot run igir"):
        igir.move([], [], "x", tmp_path / "c", (), broken)


def test_inbox_excludes() -> None:
    assert igir.inbox_excludes([Path("/in/a"), Path("/in/b")]) == (
        "/in/a/unmatched/**",
        "/in/a/duplicates/**",
        "/in/b/unmatched/**",
        "/in/b/duplicates/**",
    )


def test_nonzero_exit_includes_last_20_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", fake_which({"igir"}))
    noise = "\n".join(f"line {number}" for number in range(30))
    with pytest.raises(igir.ToolError) as error:
        run_report(tmp_path, Recorder(returncode=1, stderr=noise))
    message = str(error.value)
    assert "status 1" in message
    assert "line 29" in message
    assert "line 10" in message
    assert "line 9\n" not in message


def test_missing_report_file_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", fake_which({"igir"}))

    def quiet(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, "", "")

    with pytest.raises(igir.ToolError, match="without writing a report"):
        igir.report([Path("a.dat")], [], tmp_path / "c", None, (), quiet)


def test_report_with_unexpected_columns_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", fake_which({"igir"}))

    def odd(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        Path(argv[argv.index("--report-output") + 1]).write_text("Foo,Bar\n1,2\n")
        return subprocess.CompletedProcess(argv, 0, "", "")

    with pytest.raises(igir.ToolError, match="lacks columns"):
        igir.report([Path("a.dat")], [], tmp_path / "c", None, (), odd)


def test_unrunnable_tool_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", fake_which({"igir"}))

    def broken(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise PermissionError("denied")

    with pytest.raises(igir.ToolError, match="cannot run igir"):
        igir.report([Path("a.dat")], [], tmp_path / "c", None, (), broken)
