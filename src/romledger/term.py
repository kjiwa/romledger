import shutil
import sys
from collections.abc import Collection, Sequence
from typing import TextIO

GAP = "  "
ELLIPSIS = "…"
MIN_FLEX = 12


def width(stream: TextIO = sys.stdout) -> int | None:
    """Columns available on a terminal, or None when the output is not one."""
    return shutil.get_terminal_size().columns if stream.isatty() else None


def table(
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    right: Collection[int] = (),
    flex: int = 0,
    columns: int | None = None,
) -> list[str]:
    widths = [max(len(cells[i]) for cells in (header, *rows)) for i in range(len(header))]
    if columns is not None:
        excess = sum(widths) + len(GAP) * (len(widths) - 1) - columns
        widths[flex] = max(MIN_FLEX, widths[flex] - max(excess, 0))
    return [
        GAP.join(
            _fit(cell, size).rjust(size) if i in right else _fit(cell, size).ljust(size)
            for i, (cell, size) in enumerate(zip(cells, widths, strict=True))
        ).rstrip()
        for cells in (header, *rows)
    ]


def _fit(text: str, size: int) -> str:
    return text if len(text) <= size else text[: size - 1] + ELLIPSIS
