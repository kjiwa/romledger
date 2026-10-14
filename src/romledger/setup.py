import difflib
import json
import os
import re
import sys
import tempfile
import textwrap
from collections.abc import Collection, Mapping
from pathlib import Path

from romledger import config, registry

WIDTH = 60
DEFAULT_ROMS = "~/roms"
EXTENSION_INBOX = "~/Downloads/romledger"
NEXT_COMMANDS = ("romledger dats update", "romledger scan", "romledger serve --open")
USAGE = (
    "usage: romledger init [--roms DIR] --platform SLUG [--platform SLUG ...] [--force]. "
    "Run it on a terminal to be prompted instead."
)


def wrap(text: str, indent: str = "") -> list[str]:
    return textwrap.wrap(
        text, WIDTH, subsequent_indent=indent, break_long_words=False, break_on_hyphens=False
    )


def platform_lines(entries: Mapping[str, registry.Entry], configured: Collection[str]) -> list[str]:
    lines: list[str] = []
    for slug, entry in entries.items():
        marker = "  [configured]" if slug in configured else ""
        lines.extend(wrap(f"{slug}  {entry.dat}{marker}", "    "))
    return lines


def unknown_message(slugs: list[str], entries: Mapping[str, registry.Entry]) -> str | None:
    parts = []
    for slug in slugs:
        if slug in entries:
            continue
        near = difflib.get_close_matches(slug, entries, n=3, cutoff=0.5)
        hint = f"Nearest: {', '.join(near)}." if near else "Run romledger platforms to list them."
        parts.append(f"unknown platform {slug!r}. {hint}")
    return " ".join(parts) or None


def parse_slugs(answer: str) -> list[str]:
    return list(dict.fromkeys(slug for slug in re.split(r"[,\s]+", answer) if slug))


class Interrupted(Exception):
    pass


def read_line(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        print(file=sys.stderr)
        raise config.ConfigError("cancelled") from None
    except KeyboardInterrupt:
        print(file=sys.stderr)
        raise Interrupted from None


def ask_roms() -> str:
    return read_line(f"ROM folder [{DEFAULT_ROMS}]: ") or DEFAULT_ROMS


def ask_platforms(entries: Mapping[str, registry.Entry]) -> list[str]:
    print("Platforms romledger knows:")
    print("\n".join(platform_lines(entries, ())))
    while True:
        slugs = parse_slugs(read_line("Platforms (slugs, comma or space separated): "))
        if not slugs:
            print("Enter at least one platform.")
            continue
        message = unknown_message(slugs, entries)
        if message is None:
            return slugs
        print("\n".join(wrap(message)))


def ask_extension_inbox() -> bool:
    answer = read_line(f"Add {EXTENSION_INBOX} as an extension inbox? [y/N]: ")
    return answer.lower() in ("y", "yes")


def require_absent(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise config.ConfigError(f"{path}: already exists. Pass --force to overwrite it.")


def inbox_paths(roms: Path, extension_inbox: bool) -> list[Path]:
    inboxes = [roms / "inbox"]
    if extension_inbox:
        inboxes.append(Path(EXTENSION_INBOX).expanduser())
    return inboxes


def render_config(library: Path, inboxes: list[Path], platforms: list[str]) -> str:
    inbox_list = ", ".join(json.dumps(str(inbox)) for inbox in inboxes)
    tables = "\n".join(f"[platforms.{slug}]\n" for slug in platforms)
    return f"[library]\nroms = {json.dumps(str(library))}\ninboxes = [{inbox_list}]\n\n{tables}"


def check_creatable(directory: Path) -> None:
    ancestor = directory
    while not ancestor.exists():
        ancestor = ancestor.parent
    if not ancestor.is_dir():
        raise config.ConfigError(f"{ancestor}: not a directory. Choose another folder.")
    if not directory.exists() and not os.access(ancestor, os.W_OK | os.X_OK):
        raise config.ConfigError(f"{ancestor}: cannot create {directory}. Check its permissions.")


def check_targets(path: Path, directories: list[Path]) -> None:
    if path.is_dir():
        raise config.ConfigError(f"{path}: is a directory. Pass a config file path.")
    for directory in (*directories, path.parent):
        check_creatable(directory)


def write_config(path: Path, text: str, directories: list[Path]) -> None:
    for directory in (*directories, path.parent):
        directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=".romledger-", delete=False
    ) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(text)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def next_steps(path: Path) -> list[str]:
    lines = ["Next:", *(f"  {command}" for command in NEXT_COMMANDS)]
    if path != config.config_path(None):
        lines.extend(wrap(f"This config is not in the default place; pass --config {path}", "  "))
    return lines


def run_init(
    path: Path, roms_arg: str | None, platforms_arg: list[str], force: bool, interactive: bool
) -> None:
    entries = registry.load()
    require_absent(path, force)
    if not interactive and not platforms_arg:
        raise config.ConfigError(USAGE)
    roms_text = roms_arg or (ask_roms() if interactive else DEFAULT_ROMS)
    platforms = list(dict.fromkeys(platforms_arg)) or ask_platforms(entries)
    message = unknown_message(platforms, entries)
    if message:
        raise config.ConfigError(message)
    extension_inbox = interactive and ask_extension_inbox()
    roms = Path(roms_text).expanduser().absolute()
    inboxes = inbox_paths(roms, extension_inbox)
    library = roms / "library"
    check_targets(path, [library, *inboxes])
    write_config(path, render_config(library, inboxes, platforms), [library, *inboxes])
    print(f"wrote {path}")
    print("\n".join(next_steps(path)))


def stdin_is_terminal() -> bool:
    return sys.stdin.isatty()
