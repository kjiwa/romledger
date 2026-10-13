import argparse
import sys

from rom_scraper import __version__, config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rom-scraper",
        description="Track which retro games you have and which are missing.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", metavar="FILE", help="config file (default: see docs/setup.md)")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    commands.add_parser("config", help="validate the config file and print a summary")
    return parser


def show_config(config_arg: str | None) -> None:
    path = config.resolve_path(config_arg)
    loaded = config.load(path)
    config.check_library(loaded)
    print(f"config:  {path}")
    print(f"roms:    {loaded.library.roms}")
    for inbox in loaded.library.inboxes:
        print(f"inbox:   {inbox}")
    for slug, platform in loaded.platforms.items():
        print(f"{slug}: {platform.dat} [{', '.join(platform.regions)}]")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        show_config(args.config)
    except config.ConfigError as error:
        print(f"rom-scraper: error: {error}", file=sys.stderr)
        return 2
    return 0
