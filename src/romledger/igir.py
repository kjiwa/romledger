import csv
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

IGIR_VERSION = "5.8.0"
TAIL_LINES = 20
REPORT_COLUMNS = {"DAT Name", "Status", "Game Name", "ROM Files"}
JUNK_EXCLUDES = ("**/._*", "**/.DS_Store", "**/*.part", "**/*.crdownload", "**/*.download")
UNMATCHED_DIR = "unmatched"
UNWANTED_DIR = "unwanted"
DUPLICATES_DIR = "duplicates"
EXTRACTED_DIR = "extracted"
SET_ASIDE = (UNMATCHED_DIR, UNWANTED_DIR, DUPLICATES_DIR, EXTRACTED_DIR)


class ToolError(Exception):
    pass


@dataclass(frozen=True)
class ReportRow:
    dat: str
    status: str
    game: str
    path: str


Runner = Callable[..., Any]


def command() -> list[str]:
    if shutil.which("igir"):
        return ["igir"]
    if shutil.which("npx") and shutil.which("node"):
        return ["npx", "--yes", f"igir@{IGIR_VERSION}"]
    raise ToolError(
        "igir not found and Node.js 22.22+ (with npx) is required to run it. "
        "Install Node.js from https://nodejs.org, or install igir and put it on PATH."
    )


def inbox_excludes(inboxes: Sequence[Path]) -> tuple[str, ...]:
    return tuple(f"{inbox}/{name}/**" for inbox in inboxes for name in SET_ASIDE)


def report(
    dats: Sequence[Path],
    inputs: Sequence[Path],
    cache_path: Path,
    excludes: Sequence[str] = (),
    runner: Runner = subprocess.run,
) -> list[ReportRow]:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        output = Path(temp) / "report.csv"
        argv = _argv(["report"], dats, inputs, excludes, cache_path)
        _run([*argv, "--report-output", str(output)], runner, cache_path.parent)
        return _parse(output)


def move(
    dats: Sequence[Path],
    inputs: Sequence[Path],
    output_template: str,
    cache_path: Path,
    excludes: Sequence[str] = (),
    runner: Runner = subprocess.run,
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    argv = _argv(["move", "extract"], dats, inputs, excludes, cache_path)
    _run([*argv, "--output", output_template], runner, cache_path.parent)


def _run(argv: list[str], runner: Runner, cwd: Path) -> None:
    try:
        result = runner(argv, capture_output=True, text=True, check=False, cwd=cwd)
    except OSError as error:
        raise ToolError(f"cannot run {argv[0]}: {error}. Check that it is executable.") from error
    if result.returncode != 0:
        raise ToolError(_failure(argv, result))


def _argv(
    verbs: Sequence[str],
    dats: Sequence[Path],
    inputs: Sequence[Path],
    excludes: Sequence[str],
    cache_path: Path,
) -> list[str]:
    argv = [*command(), *verbs, "--allow-excess-sets"]
    for dat in dats:
        argv += ["--dat", str(dat)]
    for directory in inputs:
        argv += ["--input", str(directory)]
    patterns = [f"{directory}/{junk}" for directory in inputs for junk in JUNK_EXCLUDES]
    for pattern in (*patterns, *excludes):
        argv += ["--input-exclude", pattern]
    return [*argv, "--cache-path", str(cache_path)]


def _failure(argv: list[str], result: Any) -> str:
    lines = f"{result.stdout}\n{result.stderr}".strip().splitlines()[-TAIL_LINES:]
    return f"igir exited with status {result.returncode} ({' '.join(argv[:3])} ...):\n" + "\n".join(
        lines
    )


def _parse(output: Path) -> list[ReportRow]:
    if not output.is_file():
        raise ToolError(
            "igir finished without writing a report. Re-run with igir directly to see why."
        )
    with output.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = REPORT_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ToolError(
                f"igir report lacks columns {sorted(missing)}; igir {IGIR_VERSION} expected."
            )
        return [
            ReportRow(row["DAT Name"], row["Status"], row["Game Name"], row["ROM Files"])
            for row in reader
        ]
