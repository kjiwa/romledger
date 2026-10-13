from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from romledger import dats, igir, state
from romledger.config import Config, ConfigError, Platform

FOUND = "FOUND"
MISSING = "MISSING"
UNUSED = "UNUSED"
DATS_HINT = "run: romledger dats update"
SCAN_HINT = "run: romledger scan"

IgirReport = Callable[..., list[igir.ReportRow]]


def classify(
    library_rows: Sequence[igir.ReportRow], inbox_rows: Sequence[igir.ReportRow]
) -> tuple[list[state.Item], list[str]]:
    items = {
        row.game: state.Item(row.game, "have", row.path)
        for row in library_rows
        if row.status == FOUND
    }
    for row in inbox_rows:
        if row.status == FOUND and row.game not in items:
            items[row.game] = state.Item(row.game, "inbox", row.path)
    for row in library_rows:
        if row.status == MISSING and row.game not in items:
            items[row.game] = state.Item(row.game, "missing", None)
    unmatched = [row.path for row in library_rows if row.status == UNUSED]
    return list(items.values()), unmatched


def cache_path(data_dir: Path) -> Path:
    return data_dir / "igir.cache"


def require_dats(config: Config, slugs: Sequence[str], data_dir: Path) -> None:
    for slug in slugs:
        dat = dats.dat_path(data_dir, config.platforms[slug].dat)
        if not dat.is_file():
            raise ConfigError(f"no DAT for {slug} ({dat}). {DATS_HINT}")


def missing_games(data_dir: Path, slug: str) -> list[str]:
    with state.State(data_dir / "state.db") as database:
        if database.scanned_at(slug) is None:
            raise ConfigError(f"{slug} has not been scanned. {SCAN_HINT}")
        return database.missing(slug)


def scan_platform(
    config: Config, slug: str, data_dir: Path, igir_report: IgirReport = igir.report
) -> None:
    platform = config.platforms[slug]
    dat = dats.dat_path(data_dir, platform.dat)
    excludes = igir.inbox_excludes(config.library.inboxes)
    inbox_rows = _report(igir_report, dat, config.library.inboxes, platform, data_dir, excludes)
    library = config.library.roms / slug
    if library.is_dir():
        library_rows = _report(igir_report, dat, [library], platform, data_dir, ())
    else:
        # No library directory yet: everything the inbox lacks is missing.
        library_rows = [row for row in inbox_rows if row.status == MISSING]
    items, unmatched = classify(library_rows, inbox_rows)
    with state.State(data_dir / "state.db") as database:
        database.replace_platform(
            slug, items, unmatched, dats.version_of(dat), datetime.now(UTC).isoformat()
        )


def _report(
    igir_report: IgirReport,
    dat: Path,
    inputs: Sequence[Path],
    platform: Platform,
    data_dir: Path,
    excludes: Sequence[str],
) -> list[igir.ReportRow]:
    filters = igir.Filters(platform.regions, platform.languages)
    return igir_report([dat], inputs, cache_path(data_dir), filters, excludes)
