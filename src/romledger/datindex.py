import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import NamedTuple

from romledger import dats, state, titles

GAME_START = re.compile(r"^game\s*\($")
NAME_LINE = re.compile(r'^name\s+"(.*)"$')
ROM_LINE = re.compile(r"^rom\s*\((.*)\)$")
QUOTED = re.compile(r'"[^"]*"')
FIELD = re.compile(r"\b(size|crc|md5|sha1)\s+([0-9A-Za-z]+)")


class Rom(NamedTuple):
    sha1: str | None
    md5: str | None
    crc: str | None
    size: int | None
    game: str


def parse(lines: Iterable[str]) -> Iterator[Rom]:
    name: str | None = None
    fields: list[dict[str, str]] = []
    in_game = False
    for raw in lines:
        line = raw.strip()
        if not in_game:
            in_game = GAME_START.match(line) is not None
            name, fields = None, []
        elif line == ")":
            in_game = False
            if name is not None:
                yield from _roms(name, fields or [{}])
        elif (rom := ROM_LINE.match(line)) is not None:
            fields.append(dict(FIELD.findall(QUOTED.sub("", rom[1]))))
        elif name is None and (named := NAME_LINE.match(line)) is not None:
            name = named[1]


def _roms(game: str, fields: Iterable[dict[str, str]]) -> Iterator[Rom]:
    for values in fields:
        size = values.get("size", "")
        yield Rom(
            _hash(values.get("sha1")),
            _hash(values.get("md5")),
            _hash(values.get("crc")),
            int(size) if size.isdigit() else None,
            game,
        )


def _hash(value: str | None) -> str | None:
    return value.lower() if value else None


def games_of(roms: Iterable[Rom]) -> list[state.IndexedGame]:
    names = dict.fromkeys(rom.game for rom in roms)
    return [
        state.IndexedGame(game, titles.normalize(game), titles.region_of(game)) for game in names
    ]


def ensure(database: state.State, slug: str, dat: Path) -> bool:
    info = dat.stat()
    stamp = state.DatStamp(dats.version_of(dat), info.st_size, info.st_mtime_ns)
    if database.index_stamp(slug) == stamp:
        return False
    with dat.open(encoding="utf-8", errors="replace") as handle:
        roms = list(parse(handle))
    database.replace_index(slug, roms, games_of(roms), stamp)
    return True
