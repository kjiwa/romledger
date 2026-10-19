import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from romledger import catalog, datindex, dats, http, igir, state
from romledger.config import Config, ConfigError, Platform

FOUND = "FOUND"
MISSING = "MISSING"
UNUSED = "UNUSED"
SCAN_HINT = "run: romledger scan"

IgirReport = Callable[..., list[igir.ReportRow]]
ClientFactory = Callable[[str | None], httpx.Client]
Progress = Callable[[str], None]


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


def ensure_dats(
    config: Config,
    slugs: Sequence[str],
    data_dir: Path,
    client_factory: ClientFactory | None = None,
) -> list[str]:
    absent = {
        slug: config.platforms[slug].dat
        for slug in slugs
        if not dats.dat_path(data_dir, config.platforms[slug].dat).is_file()
    }
    if not absent:
        return list(slugs)
    failed: dict[str, dats.DatError] = {}
    with (client_factory or http.client)(config.network.proxy) as client:
        for slug, dat in absent.items():
            print(f"downloading the {slug} DAT ...", file=sys.stderr)
            try:
                dats.update(data_dir, {slug: dat}, client)
            except dats.DatError as error:
                failed[slug] = error
    for slug, problem in failed.items():
        print(f"romledger: warning: skipping {slug}: {problem}", file=sys.stderr)
    usable = [slug for slug in slugs if slug not in failed]
    if not usable:
        first = next(iter(failed.values()))
        raise ConfigError(f"no DAT could be downloaded ({len(failed)} failed). {first}")
    return usable


def missing_games(data_dir: Path, slug: str) -> list[str]:
    with state.State(data_dir / "state.db") as database:
        if database.scanned_at(slug) is None:
            raise ConfigError(f"{slug} has not been scanned. {SCAN_HINT}")
        return database.missing(slug)


def wanted_groups(
    database: state.State, slug: str, platform: Platform, dat: Path
) -> list[catalog.Group]:
    datindex.ensure(database, slug, dat)
    games = datindex.catalog_games(database.dat_roms(slug))
    return catalog.wanted_groups(games, platform.regions, platform.languages, platform.include)


def scan_platform(
    config: Config, slug: str, data_dir: Path, igir_report: IgirReport = igir.report
) -> None:
    scan_platforms(config, [slug], data_dir, igir_report)


def scan_platforms(
    config: Config,
    slugs: Sequence[str],
    data_dir: Path,
    igir_report: IgirReport = igir.report,
    progress: Progress = lambda _: None,
) -> None:
    if not slugs:
        return
    dat_files = {slug: dats.dat_path(data_dir, config.platforms[slug].dat) for slug in slugs}
    cache = cache_path(data_dir)
    progress("inbox")
    inbox_rows = _rows_by_dat(
        igir_report(
            list(dat_files.values()),
            config.library.inboxes,
            cache,
            igir.inbox_excludes(config.library.inboxes),
        )
    )
    for slug, dat in dat_files.items():
        progress(slug)
        with state.State(data_dir / "state.db") as database:
            groups = wanted_groups(database, slug, config.platforms[slug], dat)
        library = config.library.roms / slug
        library_rows = igir_report([dat], [library], cache, ()) if library.is_dir() else []
        items, unmatched = classify(groups, library_rows, inbox_rows.get(dats.name_of(dat), []))
        with state.State(data_dir / "state.db") as database:
            database.replace_platform(
                slug, items, unmatched, dats.version_of(dat), datetime.now(UTC).isoformat()
            )


def _rows_by_dat(rows: Sequence[igir.ReportRow]) -> dict[str, list[igir.ReportRow]]:
    grouped: dict[str, list[igir.ReportRow]] = {}
    for row in rows:
        grouped.setdefault(row.dat, []).append(row)
    return grouped
