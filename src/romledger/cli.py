import argparse
import dataclasses
import functools
import json
import os
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from romledger import (
    __version__,
    canary,
    config,
    dats,
    fetch,
    http,
    igir,
    importer,
    registry,
    scan,
    state,
)

VIMM_URL = "https://vimm.net/vault/?p=list&system={system}&q={query}"
TAGS = re.compile(r"\s*\([^)]*\)")
MIN_QUERY = 3
STATUS_COLUMNS = ("wanted", "have", "inbox", "missing", "unmatched", "done")


@dataclass(frozen=True)
class Context:
    path: Path
    config: config.Config
    platforms: dict[str, registry.Entry]
    data_dir: Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="romledger",
        description="Track which retro games you have and which are missing.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", metavar="FILE", help="config file (default: see docs/setup.md)")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    commands.add_parser("config", help="validate the config file and print a summary")
    dats_parser = commands.add_parser("dats", help="manage platform DATs")
    dats_commands = dats_parser.add_subparsers(dest="dats_command", required=True, metavar="action")
    update = dats_commands.add_parser("update", help="download the latest DATs")
    update.set_defaults(command="dats update")
    update.add_argument("platforms", nargs="*", metavar="PLATFORM", help="default: all configured")
    scan_parser = commands.add_parser("scan", help="match library and inbox files to DATs")
    scan_parser.add_argument(
        "platforms", nargs="*", metavar="PLATFORM", help="default: all configured"
    )
    import_parser = commands.add_parser("import", help="file inbox games into the library")
    import_parser.add_argument(
        "--dry-run", action="store_true", help="show what would happen; move nothing"
    )
    commands.add_parser("status", help="show have/missing counts per platform")
    fetch_parser = commands.add_parser(
        "fetch", help="download missing games from configured sources"
    )
    fetch_parser.add_argument("platform", metavar="PLATFORM")
    fetch_parser.add_argument(
        "--limit", type=positive_int, metavar="N", help="fetch at most N games"
    )
    fetch_parser.add_argument(
        "--dry-run", action="store_true", help="show matches; download nothing"
    )
    fetch_parser.add_argument(
        "--no-import", action="store_true", help="leave the downloads in the inbox"
    )
    fetch_parser.add_argument("--source", metavar="NAME", help="use only this configured source")
    canary_parser = commands.add_parser(
        "canary", help="check that the supported sites and upstream pins still match"
    )
    canary_parser.add_argument(
        "--json", action="store_true", help="print findings as JSON; notes go to stderr"
    )
    missing = commands.add_parser("missing", help="list the games a platform is missing")
    missing.add_argument("platform", metavar="PLATFORM")
    missing.add_argument("--links", action="store_true", help="append a Vimm's Lair search URL")
    return parser


def positive_int(text: str) -> int:
    if not text.isdigit() or int(text) < 1:
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive integer")
    return int(text)


def load_context(config_arg: str | None) -> Context:
    path = config.resolve_path(config_arg)
    platforms = registry.load()
    loaded = config.load(path, platforms)
    config.check_library(loaded)
    return Context(path, loaded, platforms, config.data_dir())


def selected(context: Context, names: Sequence[str]) -> list[str]:
    configured = list(context.config.platforms)
    for name in names:
        if name not in context.config.platforms:
            raise config.ConfigError(
                f"unknown platform {name!r}. Configured platforms: "
                f"{', '.join(configured) or 'none'}."
            )
    return list(dict.fromkeys(names)) or configured


def show_config(args: argparse.Namespace) -> int:
    context = load_context(args.config)
    print(f"config:  {context.path}")
    print(f"data:    {context.data_dir}")
    print(f"roms:    {context.config.library.roms}")
    for inbox in context.config.library.inboxes:
        print(f"inbox:   {inbox}")
    for slug, platform in context.config.platforms.items():
        print(f"{slug}: {platform.dat}")
        print(f"  regions: {', '.join(platform.regions)}")
        print(f"  languages: {', '.join(platform.languages)}")
        if platform.sources:
            print(f"  sources: {', '.join(platform.sources)}")
        if platform.archive_item:
            print(f"  archive_item: {platform.archive_item}")
    if context.config.network.proxy:
        print(f"proxy:   {http.redact(context.config.network.proxy)}")
    for argv in context.config.hooks.after_import:
        print(f"hook:    after_import {' '.join(argv)}")
    return 0


def update_dats(args: argparse.Namespace) -> int:
    context = load_context(args.config)
    slugs = selected(context, args.platforms)
    wanted = {slug: context.config.platforms[slug].dat for slug in slugs}
    with http.client(context.config.network.proxy) as client:
        results = dats.update(context.data_dir, wanted, client)
    for slug, result in results.items():
        print(f"{slug} {result.version} ({'updated' if result.changed else 'unchanged'})")
    return 0


def scan_platforms(args: argparse.Namespace) -> int:
    context = load_context(args.config)
    slugs = selected(context, args.platforms)
    scan.require_dats(context.config, slugs, context.data_dir)
    for slug in slugs:
        print(f"scanning {slug} ...", file=sys.stderr)
        scan.scan_platform(context.config, slug, context.data_dir)
    print(f"scanned {len(slugs)} platform(s)")
    return 0


def import_games(args: argparse.Namespace) -> int:
    return run_import(load_context(args.config), args.dry_run)


def run_import(context: Context, dry_run: bool) -> int:
    result = importer.import_inboxes(context.config, context.data_dir, dry_run)
    for line in import_lines(result, dry_run=dry_run):
        print(line)
    for failure in result.hook_failures:
        print(f"romledger: error: after_import hook failed: {failure}", file=sys.stderr)
    return 1 if result.hook_failures else 0


def import_lines(result: importer.ImportResult, *, dry_run: bool) -> list[str]:
    verb, moved_to = ("would move", "would move to") if dry_run else ("moved", "moved to")
    lines = [f"{verb} {slug} {count}" for slug, count in result.moved.items()]
    if result.duplicates:
        lines.append(
            f"duplicates {len(result.duplicates)} ({moved_to} <inbox>/{igir.DUPLICATES_DIR})"
        )
    if result.unmatched:
        lines.append(f"unmatched {len(result.unmatched)} ({moved_to} <inbox>/{igir.UNMATCHED_DIR})")
    return lines or ["inbox is empty"]


def fetch_games(args: argparse.Namespace) -> int:
    context = load_context(args.config)
    (slug,) = selected(context, [args.platform])
    if not context.config.platforms[slug].sources:
        raise config.ConfigError(f"{slug} has no sources configured; set platforms.{slug}.sources")
    with http.client(context.config.network.proxy) as client:
        throttle = http.Throttle()
        result = fetch.fetch_platform(
            context.config,
            slug,
            context.data_dir,
            args.limit,
            args.dry_run,
            functools.partial(fetch.build_sources, client=client, throttle=throttle),
            client,
            throttle,
            args.source,
        )
    status = 1 if result.failed else 0
    if result.fetched and not args.dry_run and not args.no_import:
        status = max(status, run_import(context, dry_run=False))
    return status


def show_status(args: argparse.Namespace) -> int:
    context = load_context(args.config)
    with state.State(context.data_dir / "state.db") as database:
        counts = database.counts()
    rows = [status_row(slug, counts.get(slug)) for slug in context.config.platforms]
    for line in format_table(("platform", *STATUS_COLUMNS), rows):
        print(line)
    if any(slug not in counts for slug in context.config.platforms):
        print(scan.SCAN_HINT)
    return 0


def status_row(slug: str, counts: state.Counts | None) -> tuple[str, ...]:
    if counts is None:
        return (slug, *("-" for _ in STATUS_COLUMNS))
    wanted = counts.have + counts.inbox + counts.missing
    done = f"{counts.have * 100 // wanted}%" if wanted else "-"
    values = (wanted, counts.have, counts.inbox, counts.missing, counts.unmatched)
    return (slug, *(str(value) for value in values), done)


def format_table(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    widths = [max(len(cells[i]) for cells in (header, *rows)) for i in range(len(header))]
    return [
        "  ".join(
            cell.ljust(width) if i == 0 else cell.rjust(width)
            for i, (cell, width) in enumerate(zip(cells, widths, strict=True))
        ).rstrip()
        for cells in (header, *rows)
    ]


def show_missing(args: argparse.Namespace) -> int:
    context = load_context(args.config)
    (slug,) = selected(context, [args.platform])
    games = scan.missing_games(context.data_dir, slug)
    vimm = context.platforms[slug].vimm if slug in context.platforms else None
    for game in games:
        link = vimm_link(vimm, game) if args.links and vimm else None
        print(f"{game}\t{link}" if link else game)
    return 0


def vimm_link(system: str, game: str) -> str | None:
    query = TAGS.sub("", game).strip()
    if len(query) < MIN_QUERY:
        return None
    return VIMM_URL.format(system=system, query=quote_plus(query))


def run_canary(args: argparse.Namespace) -> int:
    with http.client() as client:
        report = canary.run(
            client,
            http.Throttle(),
            registry.load(),
            registry.ignored(),
            token=os.environ.get("GITHUB_TOKEN"),
        )
    if args.json:
        payload = {
            "findings": [dataclasses.asdict(finding) for finding in report.findings],
            "inconclusive": report.inconclusive,
        }
        print(json.dumps(payload, indent=2))
    else:
        for finding in report.findings:
            print(f"finding {finding.key}: {finding.title}")
    diagnostics = sys.stderr if args.json else sys.stdout
    for note in report.notes:
        print(f"note: {note}", file=diagnostics)
    if not args.json:
        for prefix in report.inconclusive:
            print(f"unverified {prefix}")
    return 1 if report.findings else 0


HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "config": show_config,
    "dats update": update_dats,
    "scan": scan_platforms,
    "import": import_games,
    "fetch": fetch_games,
    "status": show_status,
    "missing": show_missing,
    "canary": run_canary,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return HANDLERS[args.command](args)
    except (config.ConfigError, dats.DatError, igir.ToolError) as error:
        print(f"romledger: error: {error}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except OSError as error:
        print(f"romledger: error: {error}", file=sys.stderr)
        return 2
