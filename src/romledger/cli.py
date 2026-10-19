import argparse
import dataclasses
import functools
import json
import os
import sys
import webbrowser
from collections.abc import Callable, Sequence

import uvicorn

from romledger import (
    __version__,
    canary,
    config,
    dats,
    fetch,
    http,
    igir,
    importer,
    links,
    registry,
    scan,
    setup,
    state,
    term,
)
from romledger.context import Context, load_context
from romledger.sources import SOURCES
from romledger.web import auth
from romledger.web.app import create_app

DEFAULT_HOST = "127.0.0.1"
WILDCARD_HOSTS = ("0.0.0.0", "::")  # noqa: S104
DEFAULT_PORT = 8730
STATUS_COLUMNS = ("wanted", "have", "inbox", "missing", "unmatched", "done")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="romledger",
        description="Track which retro games you have and which are missing.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="config file (default: $ROMLEDGER_CONFIG, else "
        "$XDG_CONFIG_HOME/romledger/config.toml, i.e. ~/.config/romledger/config.toml)",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    init_parser = commands.add_parser("init", help="create the config file and library folders")
    init_parser.add_argument("--roms", metavar="DIR", help="ROM folder (default: ~/roms)")
    init_parser.add_argument("--force", action="store_true", help="overwrite an existing config")
    commands.add_parser("platforms", help="list the platforms romledger knows")
    commands.add_parser("config", help="validate the config file and print a summary")
    dats_parser = commands.add_parser("dats", help="manage platform DATs")
    dats_commands = dats_parser.add_subparsers(dest="dats_command", required=True, metavar="action")
    update = dats_commands.add_parser("update", help="download the latest DATs")
    update.set_defaults(command="dats update")
    update.add_argument("platforms", nargs="*", metavar="PLATFORM", help="default: all")
    scan_parser = commands.add_parser("scan", help="match library and inbox files to DATs")
    scan_parser.add_argument("platforms", nargs="*", metavar="PLATFORM", help="default: all")
    import_parser = commands.add_parser("import", help="file inbox games into the library")
    import_parser.add_argument(
        "--dry-run", action="store_true", help="show what would happen; move nothing"
    )
    status_parser = commands.add_parser("status", help="show have/missing counts per platform")
    status_parser.add_argument(
        "--all", action="store_true", help="include platforms that have no games"
    )
    fetch_parser = commands.add_parser("fetch", help="download missing games from the sources")
    fetch_parser.add_argument(
        "platforms", nargs="*", metavar="PLATFORM", help="default: platforms that have games"
    )
    fetch_parser.add_argument(
        "--limit", type=positive_int, metavar="N", help="fetch at most N games"
    )
    fetch_parser.add_argument(
        "--dry-run", action="store_true", help="show matches; download nothing"
    )
    fetch_parser.add_argument(
        "--no-import", action="store_true", help="leave the downloads in the inbox"
    )
    fetch_parser.add_argument("--source", metavar="NAME", help="use only this source")
    canary_parser = commands.add_parser(
        "canary", help="check that the supported sites and upstream pins still match"
    )
    canary_parser.add_argument(
        "--json", action="store_true", help="print findings as JSON; notes go to stderr"
    )
    missing = commands.add_parser("missing", help="list the games a platform is missing")
    missing.add_argument("platform", metavar="PLATFORM")
    missing.add_argument(
        "--links",
        action="store_true",
        help="append the Vimm's Lair search URL, tab-separated",
    )
    serve_parser = commands.add_parser("serve", help="run the local dashboard and API")
    serve_parser.add_argument(
        "--host", default=DEFAULT_HOST, help=f"address to bind (default: {DEFAULT_HOST})"
    )
    serve_parser.add_argument(
        "--port", type=port_number, default=DEFAULT_PORT, help=f"port (default: {DEFAULT_PORT})"
    )
    serve_parser.add_argument("--open", action="store_true", help="open the dashboard in a browser")
    serve_parser.add_argument(
        "--no-auto-import",
        action="store_true",
        help="do not import inbox files automatically once they stop changing",
    )
    return parser


def port_number(text: str) -> int:
    if not text.isdigit() or not 1 <= int(text) <= 65535:
        raise argparse.ArgumentTypeError(f"{text!r} is not a port between 1 and 65535")
    return int(text)


def positive_int(text: str) -> int:
    if not text.isdigit() or int(text) < 1:
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive integer")
    return int(text)


def selected(context: Context, names: Sequence[str]) -> list[str]:
    for name in names:
        if name not in context.config.platforms:
            raise config.ConfigError(registry.unknown(name, context.platforms))
    return list(dict.fromkeys(names)) or list(context.config.platforms)


def init_config(args: argparse.Namespace) -> int:
    path = config.config_path(args.config)
    setup.run_init(path, args.roms, args.force, setup.stdin_is_terminal())
    return 0


def show_platforms(args: argparse.Namespace) -> int:
    rows = [
        (slug, entry.dat.partition("/")[2], entry.dat.partition("/")[0], _sources(entry))
        for slug, entry in registry.load().items()
    ]
    header = ("platform", "name", "dat", "sources")
    for line in term.table(header, rows, flex=1, columns=term.width()):
        print(line)
    return 0


def _sources(entry: registry.Entry) -> str:
    return ", ".join(name for name in SOURCES if getattr(entry, name)) or "-"


def show_config(args: argparse.Namespace) -> int:
    context = load_context(args.config)
    wanted = context.config.wanted
    print(f"config:  {context.path}")
    print(f"data:    {context.data_dir}")
    print(f"roms:    {context.config.library.roms}")
    for inbox in context.config.library.inboxes:
        print(f"inbox:   {inbox}")
    print(f"wanted:  {_wanted_text(wanted)}")
    for slug, platform in context.config.platforms.items():
        own = config.Wanted(platform.regions, platform.languages, platform.include)
        if own != wanted:
            print(f"{slug}:  {_wanted_text(own)}")
    if context.config.network.proxy:
        print(f"proxy:   {http.redact(context.config.network.proxy)}")
    for argv in context.config.hooks.after_import:
        print(f"hook:    after_import {' '.join(argv)}")
    return 0


def _wanted_text(wanted: config.Wanted) -> str:
    parts = [f"regions {', '.join(wanted.regions)}", f"languages {', '.join(wanted.languages)}"]
    if wanted.include:
        parts.append(f"include {', '.join(wanted.include)}")
    return "; ".join(parts)


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
    slugs = scan.ensure_dats(context.config, selected(context, args.platforms), context.data_dir)
    scan.scan_platforms(
        context.config,
        slugs,
        context.data_dir,
        progress=lambda name: print(f"scanning {name} ...", file=sys.stderr),
    )
    print(f"scanned {len(slugs)} platform(s)")
    return 0


def import_games(args: argparse.Namespace) -> int:
    return run_import(load_context(args.config), args.dry_run)


def run_import(context: Context, dry_run: bool) -> int:
    result = importer.import_inboxes(context.config, context.data_dir, dry_run)
    return importer.print_result(result, dry_run=dry_run)


def fetch_games(args: argparse.Namespace) -> int:
    context = load_context(args.config)
    if args.source:
        fetch.check_source(args.source)
    slugs = fetch_targets(context, args.platforms, args.source)
    if not slugs:
        print("nothing to fetch: no platform with games has a source; name a platform to try it")
        return 0
    failed = fetched = 0
    with http.client(context.config.network.proxy) as client:
        throttle = http.Throttle()
        for slug in slugs:
            remaining = None if args.limit is None else args.limit - fetched
            if remaining is not None and remaining <= 0:
                break
            print(f"fetching {slug} ...", file=sys.stderr)
            result = fetch.fetch_platform(
                context.config,
                slug,
                context.data_dir,
                remaining,
                args.dry_run,
                functools.partial(fetch.build_sources, client=client, throttle=throttle),
                client,
                throttle,
                args.source,
            )
            failed += len(result.failed)
            fetched += len(result.fetched)
    status = 1 if failed else 0
    if fetched and not args.dry_run and not args.no_import:
        status = max(status, run_import(context, dry_run=False))
    return status


def fetch_targets(context: Context, names: Sequence[str], source: str | None) -> list[str]:
    if names:
        slugs = selected(context, names)
        for slug in slugs:
            if not fetch.default_sources(context.config.platforms[slug]):
                raise config.ConfigError(
                    f"no source can fetch {slug}. Download it by hand into an inbox."
                )
            fetch.select_sources(slug, context.config.platforms[slug], source)
        return slugs
    with state.State(context.data_dir / "state.db") as database:
        counts = database.counts()
    return [
        slug
        for slug, platform in context.config.platforms.items()
        if has_games(counts.get(slug)) and fetch.select_sources_or_none(platform, source)
    ]


def show_status(args: argparse.Namespace) -> int:
    context = load_context(args.config)
    with state.State(context.data_dir / "state.db") as database:
        counts = database.counts()
    everything = list(context.config.platforms)
    slugs = [slug for slug in everything if args.all or has_games(counts.get(slug))]
    if slugs:
        rows = [status_row(slug, counts.get(slug)) for slug in slugs]
        header = ("platform", *STATUS_COLUMNS)
        for line in term.table(header, rows, right=range(1, len(header))):
            print(line)
    if not counts or any(slug not in counts for slug in slugs):
        print(scan.SCAN_HINT)
    elif not slugs:
        print("no games yet; put ROMs in an inbox and run: romledger import")
    elif len(slugs) < len(everything):
        print(
            f"{len(everything) - len(slugs)} platforms with no games hidden; romledger status --all"
        )
    return 0


def has_games(counts: state.Counts | None) -> bool:
    return counts is not None and counts.has_games


def status_row(slug: str, counts: state.Counts | None) -> tuple[str, ...]:
    if counts is None:
        return (slug, *("-" for _ in STATUS_COLUMNS))
    wanted = counts.have + counts.inbox + counts.missing
    done = f"{counts.have * 100 // wanted}%" if wanted else "-"
    values = (wanted, counts.have, counts.inbox, counts.missing, counts.unmatched)
    return (slug, *(str(value) for value in values), done)


def show_missing(args: argparse.Namespace) -> int:
    context = load_context(args.config)
    (slug,) = selected(context, [args.platform])
    games = scan.missing_games(context.data_dir, slug)
    entry = context.platforms.get(slug)
    for game in games:
        found = links.vimm_search(entry.vimm, game) if args.links and entry and entry.vimm else None
        print(f"{game}\t{found}" if found else game)
    return 0


def serve(args: argparse.Namespace) -> int:
    context = load_context(args.config)
    token = auth.load_token(context.data_dir)
    app = create_app(lambda: load_context(args.config), token, auto_import=not args.no_auto_import)
    link_host = "localhost" if args.host in WILDCARD_HOSTS else args.host
    url = f"http://{link_host}:{args.port}/?token={token}"
    print(f"romledger dashboard: {url}", flush=True)
    if args.open:
        webbrowser.open(url)
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)
    return 0


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
    "init": init_config,
    "platforms": show_platforms,
    "config": show_config,
    "dats update": update_dats,
    "scan": scan_platforms,
    "import": import_games,
    "fetch": fetch_games,
    "status": show_status,
    "missing": show_missing,
    "canary": run_canary,
    "serve": serve,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return HANDLERS[args.command](args)
    except (config.ConfigError, dats.DatError, igir.ToolError) as error:
        print(f"romledger: error: {error}", file=sys.stderr)
        return 2
    except setup.Interrupted:
        print("romledger: error: cancelled", file=sys.stderr)
        return 130
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except OSError as error:
        print(f"romledger: error: {error}", file=sys.stderr)
        return 2
