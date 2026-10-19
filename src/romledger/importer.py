import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from romledger import DOCS_URL, datindex, dats, igir, scan, state
from romledger.config import Config, ConfigError

NO_PLATFORMS = f"no platforms configured. Add a [platforms.<slug>] table; see {DOCS_URL}/setup.md."

IgirMove = Callable[..., None]
RunHook = Callable[[Sequence[str]], int]
PathTest = Callable[[Path], bool]
GameKey = tuple[str, str]


@dataclass(frozen=True)
class ImportResult:
    moved: dict[str, int]
    duplicates: list[Path]
    unwanted: list[Path]
    unmatched: list[Path]
    hook_failures: list[str]
    extracted: list[Path] = field(default_factory=list)


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
    with tempfile.TemporaryDirectory() as temp:
        subsets = _write_subsets(config, data_dir, Path(temp))
        return _import(config, data_dir, subsets, dry_run, igir_report, igir_move, hook)


def _import(
    config: Config,
    data_dir: Path,
    subsets: list[Path],
    dry_run: bool,
    igir_report: scan.IgirReport,
    igir_move: IgirMove,
    hook: RunHook,
) -> ImportResult:
    inboxes = config.library.inboxes
    excludes = igir.inbox_excludes(inboxes)
    cache = scan.cache_path(data_dir)
    before = igir_report(subsets, inboxes, cache, excludes)
    if not any(row.status in (scan.FOUND, scan.UNUSED) for row in before):
        return ImportResult({}, [], [], [], [])
    wanted = set(_paths(before, scan.FOUND))
    if dry_run:
        unwanted, unmatched = _leftovers(config, data_dir, igir_report, before, wanted)
        moved = _moved(config, data_dir, before, lambda _: True)
        return ImportResult(moved, [], unwanted, unmatched, [])
    library_before = _library_games(config, subsets, cache, igir_report)
    try:
        # igir has no other platform-folder token; {romm} names them by slug.
        igir_move(subsets, inboxes, f"{config.library.roms}/{{romm}}", cache, excludes)
    finally:
        _restore_inboxes(inboxes)
    after = igir_report(subsets, inboxes, cache, excludes)
    library_after = _library_games(config, subsets, cache, igir_report)
    duplicates, extracted = _split_found(after, library_before, library_after)
    moved = _moved(config, data_dir, before, lambda path: not path.exists() or path in extracted)
    duplicates = _relocate(duplicates, inboxes, igir.DUPLICATES_DIR)
    extracted = _relocate(extracted, inboxes, igir.EXTRACTED_DIR)
    unwanted, unmatched = _leftovers(config, data_dir, igir_report, before, wanted)
    unwanted = _relocate(unwanted, inboxes, igir.UNWANTED_DIR)
    unmatched = _relocate(unmatched, inboxes, igir.UNMATCHED_DIR)
    for slug in moved:
        scan.scan_platform(config, slug, data_dir, igir_report)
    hook_failures = _run_hooks(config, moved, hook)
    return ImportResult(moved, duplicates, unwanted, unmatched, hook_failures, extracted)


def import_lines(result: ImportResult, *, dry_run: bool) -> list[str]:
    verb, moved_to = ("would move", "would move to") if dry_run else ("moved", "moved to")
    lines = [f"{verb} {slug} {count}" for slug, count in result.moved.items()]
    if result.extracted:
        lines.append(f"extracted {len(result.extracted)} ({moved_to} <inbox>/{igir.EXTRACTED_DIR})")
    if result.duplicates:
        lines.append(
            f"duplicates {len(result.duplicates)} ({moved_to} <inbox>/{igir.DUPLICATES_DIR})"
        )
    if result.unwanted:
        lines.append(f"unwanted {len(result.unwanted)} ({moved_to} <inbox>/{igir.UNWANTED_DIR})")
    if result.unmatched:
        lines.append(f"unmatched {len(result.unmatched)} ({moved_to} <inbox>/{igir.UNMATCHED_DIR})")
    return lines or ["inbox is empty"]


def print_result(result: ImportResult, *, dry_run: bool) -> int:
    for line in import_lines(result, dry_run=dry_run):
        print(line)
    for failure in result.hook_failures:
        print(f"romledger: error: after_import hook failed: {failure}", file=sys.stderr)
    return 1 if result.hook_failures else 0


def _write_subsets(config: Config, data_dir: Path, directory: Path) -> list[Path]:
    subsets = []
    with state.State(data_dir / "state.db") as database:
        for slug, platform in config.platforms.items():
            dat = dats.dat_path(data_dir, platform.dat)
            groups = scan.wanted_groups(database, slug, platform, dat)
            wanted = {name for group in groups for name in group.members}
            roms = [rom for rom in database.dat_roms(slug) if rom.game in wanted]
            subsets.append(directory / f"{slug}.dat")
            datindex.write_subset(subsets[-1], dats.name_of(dat), roms)
    return subsets


def _leftovers(
    config: Config,
    data_dir: Path,
    igir_report: scan.IgirReport,
    before: Sequence[igir.ReportRow],
    wanted: set[Path],
) -> tuple[list[Path], list[Path]]:
    if not _paths(before, scan.UNUSED):
        return [], []
    full = [dats.dat_path(data_dir, platform.dat) for platform in config.platforms.values()]
    inboxes = config.library.inboxes
    rows = igir_report(full, inboxes, scan.cache_path(data_dir), igir.inbox_excludes(inboxes))
    unwanted = [path for path in _paths(rows, scan.FOUND) if path not in wanted]
    return unwanted, _paths(rows, scan.UNUSED)


def _library_games(
    config: Config, subsets: list[Path], cache: Path, igir_report: scan.IgirReport
) -> set[GameKey]:
    roms = config.library.roms
    if not roms.is_dir():
        return set()
    rows = igir_report(subsets, [roms], cache, ())
    return {(row.dat, row.game) for row in rows if row.status == scan.FOUND}


def _split_found(
    after: Sequence[igir.ReportRow], library_before: set[GameKey], library_after: set[GameKey]
) -> tuple[list[Path], list[Path]]:
    games: dict[Path, set[GameKey]] = {}
    for row in after:
        if row.status == scan.FOUND and row.path:
            games.setdefault(Path(row.path), set()).add((row.dat, row.game))
    duplicates, extracted = [], []
    for path, keys in games.items():
        if keys <= library_before:
            duplicates.append(path)
        elif keys <= library_after:
            extracted.append(path)
        else:
            print(f"romledger: warning: {path} was not imported; left in place", file=sys.stderr)
    return duplicates, extracted


def _restore_inboxes(inboxes: Sequence[Path]) -> None:
    for inbox in inboxes:
        inbox.mkdir(parents=True, exist_ok=True)


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
