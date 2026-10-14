import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from xml.sax.saxutils import quoteattr

from romledger import catalog, dats, state, titles

GAME_START = re.compile(r"^game\s*\($")
NAME_LINE = re.compile(r'^name\s+"(.*)"$')
ROM_LINE = re.compile(r"^rom\s*\((.*)\)$")
QUOTED = re.compile(r'"[^"]*"')
FIELD = re.compile(r"\b(size|crc|md5|sha1)\s+([0-9A-Za-z]+)")
ROM_NAME = re.compile(r'\bname\s+"((?:[^"\\]|\\.)*)"')
ESCAPE = re.compile(r"\\(.)")


def parse(lines: Iterable[str]) -> Iterator[state.DatRom]:
    name: str | None = None
    fields: list[dict[str, str]] = []
    in_game = False
    block = -1
    for raw in lines:
        line = raw.strip()
        if not in_game:
            in_game = GAME_START.match(line) is not None
            name, fields = None, []
            if in_game:
                block += 1
        elif line == ")":
            in_game = False
            if name is not None:
                yield from _roms(name, fields or [{}], block)
        elif (rom := ROM_LINE.match(line)) is not None:
            fields.append(_rom_fields(rom[1]))
        elif name is None and (named := NAME_LINE.match(line)) is not None:
            name = named[1]


def _rom_fields(text: str) -> dict[str, str]:
    fields = dict(FIELD.findall(QUOTED.sub("", text)))
    if (named := ROM_NAME.search(text)) is not None:
        fields["name"] = ESCAPE.sub(r"\1", named[1])
    return fields


def _roms(game: str, fields: Iterable[dict[str, str]], block: int) -> Iterator[state.DatRom]:
    for values in fields:
        size = values.get("size", "")
        yield state.DatRom(
            _hash(values.get("sha1")),
            _hash(values.get("md5")),
            _hash(values.get("crc")),
            int(size) if size.isdigit() else None,
            game,
            values.get("name"),
            block,
        )


def _hash(value: str | None) -> str | None:
    return value.lower() if value else None


def games_of(roms: Iterable[state.DatRom]) -> list[state.IndexedGame]:
    names = dict.fromkeys(rom.game for rom in roms)
    return [
        state.IndexedGame(game, titles.normalize(game), titles.region_of(game)) for game in names
    ]


def catalog_games(roms: Iterable[state.DatRom]) -> list[catalog.Game]:
    names: dict[str, list[str]] = {}
    for rom in roms:
        names.setdefault(rom.game, [])
        if rom.name is not None:
            names[rom.game].append(rom.name)
    return [catalog.Game(game, tuple(rom_names)) for game, rom_names in names.items()]


def write_subset(path: Path, dat_name: str, roms: Iterable[state.DatRom]) -> None:
    blocks: dict[tuple[str, int], list[state.DatRom]] = {}
    for rom in roms:
        blocks.setdefault((rom.game, rom.block), []).append(rom)
    lines = [
        '<?xml version="1.0"?>',
        f"<datafile><header><name>{_text(dat_name)}</name></header>",
        *(_game_xml(game, block_roms) for (game, _), block_roms in blocks.items()),
        "</datafile>",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _game_xml(game: str, roms: Iterable[state.DatRom]) -> str:
    return f"<game name={quoteattr(game)}>{''.join(_rom_xml(rom) for rom in roms)}</game>"


def _rom_xml(rom: state.DatRom) -> str:
    if rom.name is None:
        return ""
    attributes = {"size": rom.size, "crc": rom.crc, "md5": rom.md5, "sha1": rom.sha1}
    fields = "".join(
        f" {key}={quoteattr(str(value))}" for key, value in attributes.items() if value is not None
    )
    return f"<rom name={quoteattr(rom.name)}{fields}/>"


def _text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ensure(database: state.State, slug: str, dat: Path) -> bool:
    info = dat.stat()
    stamp = state.DatStamp(dats.version_of(dat), info.st_size, info.st_mtime_ns)
    if database.index_stamp(slug) == stamp:
        return False
    with dat.open(encoding="utf-8", errors="replace") as handle:
        roms = list(parse(handle))
    database.replace_index(slug, roms, games_of(roms), stamp)
    return True
