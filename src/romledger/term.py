import os
import shutil
import sys
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import TextIO

GAP = "  "
ELLIPSIS = "…"
MIN_FLEX = 12
STYLES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33"}
# The first words of a result line and how they are colored. Lines stay plain text when piped.
VERBS = {
    "moved": "green",
    "extracted": "green",
    "fetched": "green",
    "updated": "green",
    "connected": "green",
    "wrote": "green",
    "removed": "green",
    "would": "dim",
    "unchanged": "dim",
    "not found": "yellow",
    "skipped": "yellow",
    "duplicates": "yellow",
    "unwanted": "yellow",
    "unmatched": "yellow",
    "failed": "red",
}

CellStyle = Callable[[int, str], str | None]


def width(stream: TextIO | None = None) -> int | None:
    stream = stream or sys.stdout
    return shutil.get_terminal_size().columns if stream.isatty() else None


def color_enabled(stream: TextIO | None = None, env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    if env.get("NO_COLOR"):
        return False
    if env.get("FORCE_COLOR"):
        return True
    if env.get("TERM") == "dumb":
        return False
    return (stream or sys.stdout).isatty()


def paint(text: str, style: str, enabled: bool) -> str:
    return f"\x1b[{STYLES[style]}m{text}\x1b[0m" if enabled and text else text


def table(
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    right: Collection[int] = (),
    flex: int = 0,
    columns: int | None = None,
    enabled: bool = False,
    cell_style: CellStyle | None = None,
) -> list[str]:
    widths = [max(len(cells[i]) for cells in (header, *rows)) for i in range(len(header))]
    if columns is not None:
        excess = sum(widths) + len(GAP) * (len(widths) - 1) - columns
        widths[flex] = max(MIN_FLEX, widths[flex] - max(excess, 0))

    def line(cells: Sequence[str], styled: bool, heading: bool) -> str:
        out = []
        for i, (cell, size) in enumerate(zip(cells, widths, strict=True)):
            text = _fit(cell, size)
            style = "bold" if heading else (cell_style(i, cell) if styled and cell_style else None)
            padding = " " * (size - len(text))
            colored = paint(text, style, enabled) if style else text
            out.append(padding + colored if i in right else colored + padding)
        return GAP.join(out).rstrip()

    return [line(header, False, True), *(line(cells, True, False) for cells in rows)]


def _fit(text: str, size: int) -> str:
    return text if len(text) <= size else text[: size - 1] + ELLIPSIS


def say(line: str, stream: TextIO | None = None) -> None:
    stream = stream or sys.stdout
    enabled = color_enabled(stream)
    if enabled:
        for verb, style in VERBS.items():
            if line == verb or line.startswith(f"{verb} "):
                line = paint(verb, style, True) + line[len(verb) :]
                break
    print(line, file=stream)


def error(message: str) -> None:
    label = paint("error:", "red", color_enabled(sys.stderr))
    print(f"romledger: {label} {message}", file=sys.stderr)


def warning(message: str) -> None:
    label = paint("warning:", "yellow", color_enabled(sys.stderr))
    print(f"romledger: {label} {message}", file=sys.stderr)


def note(message: str) -> None:
    print(message, file=sys.stderr)


def stderr_is_tty() -> bool:
    return sys.stderr.isatty()


def progress(message: str) -> None:
    if stderr_is_tty():
        print(message, file=sys.stderr)
