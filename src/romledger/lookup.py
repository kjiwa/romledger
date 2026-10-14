import re
from collections.abc import Sequence
from dataclasses import dataclass

from romledger import state, titles

HAVE = "have"
INBOX = "inbox"
MISSING = "missing"
UNWANTED = "unwanted"
UNSCANNED = "unscanned"
UNKNOWN = "unknown"
WANTED = (HAVE, INBOX, MISSING)
TAG = re.compile(r"\(([^()]*)\)")


@dataclass(frozen=True)
class Match:
    platform: str | None
    game: str | None
    state: str
    exact: bool


def by_hash(database: state.State, sha1: str) -> list[Match]:
    found = database.locate_sha1(sha1.lower())
    if not found:
        return [Match(None, None, UNKNOWN, True)]
    return [_match(item, exact=True) for item in found]


def by_name(
    database: state.State, platform: str, name: str, regions: Sequence[str] = ()
) -> list[Match]:
    exact = database.locate_game(platform, name)
    if exact:
        return [_match(exact[0], exact=True)]
    normalized = titles.normalize(name)
    candidates = database.locate_title(platform, normalized) if normalized else []
    if not candidates:
        return [Match(platform, name, UNKNOWN, False)]
    wanted_regions: set[str | None] = {titles.region_name(region) for region in regions} or {
        titles.region_of(name)
    }
    pool = _narrow(_with_tags(candidates, _tokens(name)), wanted_regions)
    return [_match(item, exact=False) for item in pool]


def _tokens(game: str) -> set[str]:
    return {
        token.strip().lower()
        for tag in TAG.findall(game)
        for token in tag.split(",")
        if token.strip()
    }


def _with_tags(candidates: list[state.Located], tokens: set[str]) -> list[state.Located]:
    return [item for item in candidates if tokens <= _tokens(item.game)] or candidates


def _narrow(candidates: list[state.Located], regions: set[str | None]) -> list[state.Located]:
    pool = [item for item in candidates if item.region in regions] or candidates
    wanted = [item for item in pool if item.state in WANTED]
    return wanted if len(pool) > 1 and len(wanted) == 1 else pool


def _match(item: state.Located, *, exact: bool) -> Match:
    return Match(item.platform, item.game, _state_of(item), exact)


def _state_of(item: state.Located) -> str:
    if not item.scanned:
        return UNSCANNED
    return item.state or UNWANTED
