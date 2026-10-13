import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

SCHEMA_VERSION = 1
SCHEMA = """
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


class State:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        if self._db.execute("PRAGMA user_version").fetchone()[0] == 0:
            with self._db:
                self._db.executescript(SCHEMA)
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
