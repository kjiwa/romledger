import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import NamedTuple

SCHEMA_VERSION = 4
BASE_SCHEMA = """
CREATE TABLE entries (
    platform TEXT NOT NULL,
    game TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('have', 'inbox', 'missing')),
    path TEXT,
    PRIMARY KEY (platform, game)
);
CREATE TABLE unmatched (platform TEXT NOT NULL, path TEXT NOT NULL);
CREATE TABLE scans (
    platform TEXT PRIMARY KEY,
    scanned_at TEXT NOT NULL,
    dat_version TEXT NOT NULL
);
"""
INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS dat_index (
    platform TEXT NOT NULL,
    game TEXT NOT NULL,
    sha1 TEXT,
    md5 TEXT,
    crc TEXT,
    size INTEGER,
    rom TEXT,
    block INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS dat_index_sha1 ON dat_index (sha1);
CREATE INDEX IF NOT EXISTS dat_index_game ON dat_index (platform, game);
CREATE TABLE IF NOT EXISTS dat_games (
    platform TEXT NOT NULL,
    game TEXT NOT NULL,
    norm TEXT NOT NULL,
    region TEXT,
    PRIMARY KEY (platform, game)
);
CREATE INDEX IF NOT EXISTS dat_games_norm ON dat_games (platform, norm);
CREATE TABLE IF NOT EXISTS dat_versions (
    platform TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL
);
"""
RESET_SCANS = """
DROP TABLE IF EXISTS dat_index;
DROP TABLE IF EXISTS dat_games;
DROP TABLE IF EXISTS dat_versions;
DELETE FROM entries;
DELETE FROM unmatched;
DELETE FROM scans;
"""
REBUILD_INDEX = """
DROP TABLE IF EXISTS dat_index;
DROP TABLE IF EXISTS dat_versions;
"""
MIGRATIONS = {
    0: BASE_SCHEMA + INDEX_SCHEMA,
    1: RESET_SCANS + INDEX_SCHEMA,
    2: RESET_SCANS + INDEX_SCHEMA,
    3: REBUILD_INDEX + INDEX_SCHEMA,
}


class DatStamp(NamedTuple):
    version: str
    size: int
    mtime_ns: int


class DatRom(NamedTuple):
    sha1: str | None
    md5: str | None
    crc: str | None
    size: int | None
    game: str
    name: str | None
    block: int


@dataclass(frozen=True)
class Item:
    game: str
    state: str
    path: str | None


@dataclass(frozen=True)
class Counts:
    have: int
    inbox: int
    missing: int
    unmatched: int


@dataclass(frozen=True)
class IndexedGame:
    game: str
    norm: str
    region: str | None


@dataclass(frozen=True)
class Located:
    platform: str
    game: str
    region: str | None
    state: str | None
    scanned: bool


LOCATE = """
SELECT g.platform, g.game, g.region, e.state, s.platform IS NOT NULL
FROM dat_games g
LEFT JOIN (
    SELECT x.platform, x.game, d.norm, x.state
    FROM entries x JOIN dat_games d ON d.platform = x.platform AND d.game = x.game
) e ON e.platform = g.platform AND (e.game = g.game OR (g.norm != '' AND e.norm = g.norm))
LEFT JOIN scans s ON s.platform = g.platform
WHERE {where}
ORDER BY g.platform, g.game
"""


class State:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version in MIGRATIONS:
            with self._db:
                self._db.executescript(MIGRATIONS[version])
                self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def __enter__(self) -> "State":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._db.close()

    def replace_platform(
        self,
        platform: str,
        entries: Iterable[Item],
        unmatched: Iterable[str],
        dat_version: str,
        now: str,
    ) -> None:
        with self._db:
            for table in ("entries", "unmatched"):
                self._db.execute(f"DELETE FROM {table} WHERE platform = ?", (platform,))  # noqa: S608
            self._db.executemany(
                "INSERT INTO entries VALUES (?, ?, ?, ?)",
                [(platform, item.game, item.state, item.path) for item in entries],
            )
            self._db.executemany(
                "INSERT INTO unmatched VALUES (?, ?)", [(platform, path) for path in unmatched]
            )
            self._db.execute(
                "INSERT OR REPLACE INTO scans VALUES (?, ?, ?)", (platform, now, dat_version)
            )

    def counts(self) -> dict[str, Counts]:
        rows = self._db.execute(
            """
            SELECT scans.platform,
              COALESCE(SUM(entries.state = 'have'), 0),
              COALESCE(SUM(entries.state = 'inbox'), 0),
              COALESCE(SUM(entries.state = 'missing'), 0),
              (SELECT COUNT(*) FROM unmatched WHERE unmatched.platform = scans.platform)
            FROM scans LEFT JOIN entries ON entries.platform = scans.platform
            GROUP BY scans.platform
            """
        )
        return {row[0]: Counts(*row[1:]) for row in rows}

    def missing(self, platform: str) -> list[str]:
        rows = self._db.execute(
            "SELECT game FROM entries WHERE platform = ? AND state = 'missing' ORDER BY game",
            (platform,),
        )
        return [row[0] for row in rows]

    def scanned_at(self, platform: str) -> str | None:
        row = self._db.execute(
            "SELECT scanned_at FROM scans WHERE platform = ?", (platform,)
        ).fetchone()
        return None if row is None else str(row[0])

    def entries(
        self, platform: str, states: Sequence[str], query: str, limit: int, offset: int
    ) -> tuple[list[Item], int]:
        where, args = self._entry_filter(platform, states, query)
        total = self._db.execute(f"SELECT COUNT(*) FROM entries WHERE {where}", args)  # noqa: S608
        rows = self._db.execute(
            f"SELECT game, state, path FROM entries WHERE {where} "  # noqa: S608
            "ORDER BY game LIMIT ? OFFSET ?",
            (*args, limit, offset),
        )
        return [Item(*row) for row in rows], int(total.fetchone()[0])

    def index_stamp(self, platform: str) -> DatStamp | None:
        row = self._db.execute(
            "SELECT version, size, mtime_ns FROM dat_versions WHERE platform = ?", (platform,)
        ).fetchone()
        return None if row is None else DatStamp(*row)

    def replace_index(
        self,
        platform: str,
        roms: Iterable[DatRom],
        games: Iterable[IndexedGame],
        stamp: DatStamp,
    ) -> None:
        with self._db:
            for table in ("dat_index", "dat_games"):
                self._db.execute(f"DELETE FROM {table} WHERE platform = ?", (platform,))  # noqa: S608
            self._db.executemany(
                "INSERT INTO dat_index (platform, sha1, md5, crc, size, game, rom, block) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(platform, *rom) for rom in roms],
            )
            self._db.executemany(
                "INSERT INTO dat_games VALUES (?, ?, ?, ?)",
                [(platform, item.game, item.norm, item.region) for item in games],
            )
            self._db.execute(
                "INSERT OR REPLACE INTO dat_versions VALUES (?, ?, ?, ?)", (platform, *stamp)
            )

    def dat_roms(self, platform: str) -> list[DatRom]:
        rows = self._db.execute(
            "SELECT sha1, md5, crc, size, game, rom, block FROM dat_index WHERE platform = ? "
            "ORDER BY game, block, rowid",
            (platform,),
        )
        return [DatRom(*row) for row in rows]

    def locate_sha1(self, sha1: str) -> list[Located]:
        where = "(g.platform, g.game) IN (SELECT platform, game FROM dat_index WHERE sha1 = ?)"
        return self._locate(where, (sha1,))

    def locate_game(self, platform: str, game: str) -> list[Located]:
        return self._locate("g.platform = ? AND g.game = ?", (platform, game))

    def locate_title(self, platform: str, norm: str) -> list[Located]:
        return self._locate("g.platform = ? AND g.norm = ?", (platform, norm))

    def _locate(self, where: str, args: tuple[str, ...]) -> list[Located]:
        rows = self._db.execute(LOCATE.format(where=where), args)
        return [Located(row[0], row[1], row[2], row[3], bool(row[4])) for row in rows]

    @staticmethod
    def _entry_filter(
        platform: str, states: Sequence[str], query: str
    ) -> tuple[str, tuple[str, ...]]:
        where, args = ["platform = ?"], [platform]
        if states:
            where.append(f"state IN ({', '.join('?' * len(states))})")
            args.extend(states)
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append("game LIKE ? ESCAPE '\\'")
            args.append(f"%{escaped}%")
        return " AND ".join(where), tuple(args)
