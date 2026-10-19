import json
import os
import sys
import tempfile
from pathlib import Path

from romledger import config

DEFAULT_ROMS = "~/roms"
EXTENSION_INBOX = "~/Downloads/romledger"
NEXT_COMMANDS = ("romledger import", "romledger status")
CONFIG_HINTS = """\
# Optional. What each platform wants; these are the defaults.
# [wanted]
# regions = ["USA", "WORLD"]
# languages = ["EN"]
# include = []
#
# Override them for one platform; `romledger platforms` lists the names.
# [platforms.snes]
# regions = ["USA", "JPN"]
"""


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


def render_config(library: Path, inboxes: list[Path]) -> str:
    inbox_list = ", ".join(json.dumps(str(inbox)) for inbox in inboxes)
    return (
        f"[library]\nroms = {json.dumps(str(library))}\ninboxes = [{inbox_list}]\n\n{CONFIG_HINTS}"
    )


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


def next_steps(path: Path, inbox: Path) -> list[str]:
    lines = [f"Put ROMs in {inbox}, then:", *(f"  {command}" for command in NEXT_COMMANDS)]
    if path != config.config_path(None):
        lines.append(f"This config is not in the default place; pass --config {path}")
    return lines


def run_init(path: Path, roms_arg: str | None, force: bool, interactive: bool) -> None:
    require_absent(path, force)
    roms_text = roms_arg or (ask_roms() if interactive else DEFAULT_ROMS)
    extension_inbox = interactive and ask_extension_inbox()
    roms = Path(roms_text).expanduser().absolute()
    inboxes = inbox_paths(roms, extension_inbox)
    library = roms / "library"
    check_targets(path, [library, *inboxes])
    write_config(path, render_config(library, inboxes), [library, *inboxes])
    print(f"wrote {path}")
    print("\n".join(next_steps(path, inboxes[0])))


def stdin_is_terminal() -> bool:
    return sys.stdin.isatty()
