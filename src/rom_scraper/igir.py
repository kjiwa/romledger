import csv
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

IGIR_VERSION = "5.7.2"
TAIL_LINES = 20


class ToolError(Exception):
    pass


@dataclass(frozen=True)
class ReportRow:
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


def report(
    dat: Path,
    inputs: Sequence[Path],
    regions: Sequence[str],
    languages: Sequence[str],
    cache_path: Path,
    runner: Runner = subprocess.run,
) -> list[ReportRow]:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        output = Path(temp) / "report.csv"
        argv = _argv(command(), dat, inputs, regions, languages, cache_path, output)
        result = runner(argv, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise ToolError(_failure(argv, result))
        return _parse(output)


def _argv(
    base: list[str],
    dat: Path,
    inputs: Sequence[Path],
    regions: Sequence[str],
    languages: Sequence[str],
    cache_path: Path,
    output: Path,
) -> list[str]:
    argv = [*base, "report", "--dat", str(dat)]
    for directory in inputs:
        argv += ["--input", str(directory)]
    return [
        *argv,
        "--single",
        "--filter-region",
        ",".join(regions),
        "--filter-language",
        ",".join(languages),
        "--prefer-region",
        ",".join(regions),
        "--prefer-language",
        ",".join(languages),
        "--cache-path",
        str(cache_path),
        "--report-output",
        str(output),
    ]


def _failure(argv: list[str], result: Any) -> str:
    lines = f"{result.stdout}\n{result.stderr}".strip().splitlines()[-TAIL_LINES:]
    return f"igir exited with status {result.returncode} ({' '.join(argv[:3])} ...):\n" + "\n".join(
        lines
    )


def _parse(output: Path) -> list[ReportRow]:
    if not output.is_file():
        return []
    with output.open(newline="", encoding="utf-8") as handle:
        return [_row(row) for row in csv.DictReader(handle)]


def _row(row: dict[str, str]) -> ReportRow:
    return ReportRow(row["Status"], row["Game Name"], row["ROM Files"])
