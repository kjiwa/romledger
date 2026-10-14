import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from romledger import DOCS_URL, dats, igir, scan
from romledger.config import Config, ConfigError

NO_PLATFORMS = f"no platforms configured. Add a [platforms.<slug>] table; see {DOCS_URL}/setup.md."

IgirMove = Callable[..., None]
RunHook = Callable[[Sequence[str]], int]
PathTest = Callable[[Path], bool]


@dataclass(frozen=True)
class ImportResult:
    moved: dict[str, int]
    duplicates: list[Path]
    unmatched: list[Path]
    hook_failures: list[str]


def run_hook(argv: Sequence[str]) -> int:
    return subprocess.run(argv, check=False).returncode  # noqa: S603


def import_inboxes(
    config: Config,
    data_dir: Path,
    dry_run: bool,
    igir_report: scan.IgirReport = igir.report,
    igir_move: IgirMove = igir.move,
    hook: RunHook = run_hook,
) -> ImportResult:
    slugs = list(config.platforms)
    if not slugs:
        raise ConfigError(NO_PLATFORMS)
    scan.require_dats(config, slugs, data_dir)
    dat_files = [dats.dat_path(data_dir, config.platforms[slug].dat) for slug in slugs]
    inboxes = config.library.inboxes
    excludes = igir.inbox_excludes(inboxes)
    cache = scan.cache_path(data_dir)
    before = igir_report(dat_files, inboxes, cache, None, excludes)
    if not any(row.status in (scan.FOUND, scan.UNUSED) for row in before):
        return ImportResult({}, [], [], [])
    if dry_run:
        return ImportResult(
            _moved(config, data_dir, before, lambda _: True), [], _paths(before, scan.UNUSED), []
        )
    igir_move(dat_files, inboxes, f"{config.library.roms}/{{romm}}", cache, excludes)
    after = igir_report(dat_files, inboxes, cache, None, excludes)
    moved = _moved(config, data_dir, before, lambda path: not path.exists())
    duplicates = _relocate(_paths(after, scan.FOUND), inboxes, igir.DUPLICATES_DIR)
    unmatched = _relocate(_paths(after, scan.UNUSED), inboxes, igir.UNMATCHED_DIR)
    for slug in moved:
        scan.scan_platform(config, slug, data_dir, igir_report)
    return ImportResult(moved, duplicates, unmatched, _run_hooks(config, moved, hook))


def import_lines(result: ImportResult, *, dry_run: bool) -> list[str]:
    verb, moved_to = ("would move", "would move to") if dry_run else ("moved", "moved to")
    lines = [f"{verb} {slug} {count}" for slug, count in result.moved.items()]
    if result.duplicates:
        lines.append(
            f"duplicates {len(result.duplicates)} ({moved_to} <inbox>/{igir.DUPLICATES_DIR})"
        )
    if result.unmatched:
        lines.append(f"unmatched {len(result.unmatched)} ({moved_to} <inbox>/{igir.UNMATCHED_DIR})")
    return lines or ["inbox is empty"]


def print_result(result: ImportResult, *, dry_run: bool) -> int:
    for line in import_lines(result, dry_run=dry_run):
        print(line)
    for failure in result.hook_failures:
        print(f"romledger: error: after_import hook failed: {failure}", file=sys.stderr)
    return 1 if result.hook_failures else 0


def _paths(rows: Sequence[igir.ReportRow], status: str) -> list[Path]:
    return list(dict.fromkeys(Path(row.path) for row in rows if row.status == status and row.path))


def _moved(
    config: Config, data_dir: Path, rows: Sequence[igir.ReportRow], gone: PathTest
) -> dict[str, int]:
    slugs = {
        dats.name_of(dats.dat_path(data_dir, platform.dat)): slug
        for slug, platform in config.platforms.items()
    }
    files: dict[str, set[Path]] = {}
    for row in rows:
        if row.status == scan.FOUND and row.dat in slugs and gone(Path(row.path)):
            files.setdefault(slugs[row.dat], set()).add(Path(row.path))
    return {slug: len(paths) for slug, paths in files.items()}


def _relocate(paths: Sequence[Path], inboxes: Sequence[Path], directory: str) -> list[Path]:
    relocated = []
    for path in paths:
        inbox = next((inbox for inbox in inboxes if path.is_relative_to(inbox)), None)
        if inbox is None:
            print(
                f"romledger: warning: {path} is not under any inbox; left in place",
                file=sys.stderr,
            )
            continue
        destination = free_path(inbox / directory / path.relative_to(inbox))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(path, destination)
        relocated.append(destination)
    return relocated


def free_path(path: Path) -> Path:
    candidate, number = path, 0
    while candidate.exists():
        number += 1
        candidate = path.with_name(f"{path.stem}.{number}{path.suffix}")
    return candidate


def _run_hooks(config: Config, moved: dict[str, int], hook: RunHook) -> list[str]:
    if not moved:
        return []
    failures = []
    for argv in config.hooks.after_import:
        try:
            status = hook(argv)
        except OSError as error:
            failures.append(f"{' '.join(argv)}: {error}")
        else:
            if status != 0:
                failures.append(f"{' '.join(argv)}: exit status {status}")
    return failures
