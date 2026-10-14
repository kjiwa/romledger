import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from romledger import catalog, datindex, dats, igir, state
from romledger.config import Config, ConfigError, Platform

FOUND = "FOUND"
MISSING = "MISSING"
UNUSED = "UNUSED"
DATS_HINT = "run: romledger dats update"
SCAN_HINT = "run: romledger scan"

IgirReport = Callable[..., list[igir.ReportRow]]


def classify(
    groups: Sequence[catalog.Group],
    library_rows: Sequence[igir.ReportRow],
    inbox_rows: Sequence[igir.ReportRow],
) -> tuple[list[state.Item], list[str]]:
    library, inbox = _found(library_rows), _found(inbox_rows)
    items = [_item(group, library, inbox) for group in groups]
    unmatched = [row.path for row in library_rows if row.status == UNUSED]
    return items, unmatched


def _found(rows: Sequence[igir.ReportRow]) -> dict[str, str]:
    found: dict[str, str] = {}
    for row in rows:
        if row.status == FOUND:
            found.setdefault(row.game, row.path)
    return found


def _item(group: catalog.Group, library: dict[str, str], inbox: dict[str, str]) -> state.Item:
    for kind, found in (("have", library), ("inbox", inbox)):
        member = next((name for name in group.members if name in found), None)
        if member is not None:
            return state.Item(member, kind, found[member])
    return state.Item(group.preferred, "missing", None)


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


def scan_each(slugs: Sequence[str], scan_one: Callable[[str], None]) -> None:
    for slug in slugs:
        print(f"scanning {slug} ...", file=sys.stderr)
        scan_one(slug)
    print(f"scanned {len(slugs)} platform(s)")


def wanted_groups(
    database: state.State, slug: str, platform: Platform, dat: Path
) -> list[catalog.Group]:
    datindex.ensure(database, slug, dat)
    games = datindex.catalog_games(database.dat_roms(slug))
    return catalog.wanted_groups(games, platform.regions, platform.languages, platform.include)


def scan_platform(
    config: Config, slug: str, data_dir: Path, igir_report: IgirReport = igir.report
) -> None:
    platform = config.platforms[slug]
    dat = dats.dat_path(data_dir, platform.dat)
    with state.State(data_dir / "state.db") as database:
        groups = wanted_groups(database, slug, platform, dat)
    cache = cache_path(data_dir)
    excludes = igir.inbox_excludes(config.library.inboxes)
    inbox_rows = igir_report([dat], config.library.inboxes, cache, excludes)
    library = config.library.roms / slug
    library_rows = igir_report([dat], [library], cache, ()) if library.is_dir() else []
    items, unmatched = classify(groups, library_rows, inbox_rows)
    with state.State(data_dir / "state.db") as database:
        database.replace_platform(
            slug, items, unmatched, dats.version_of(dat), datetime.now(UTC).isoformat()
        )
