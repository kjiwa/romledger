import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from romledger import igir, links, registry, state
from romledger.context import Context

PAGE_SIZE = 200
STATE_FILTERS = ("missing", "inbox", "have", "all")
JUNK_NAMES = (".DS_Store",)
JUNK_PREFIX = "._"
PART_SUFFIX = ".part"


@dataclass(frozen=True)
class PlatformView:
    slug: str
    name: str
    scanned_at: str | None
    counts: state.Counts | None

    @property
    def tracked(self) -> bool:
        return self.counts is not None and self.counts.has_games

    @property
    def wanted(self) -> int:
        counts = self.counts
        return counts.have + counts.inbox + counts.missing if counts else 0

    @property
    def percent(self) -> int | None:
        wanted = self.wanted
        return self.counts.have * 100 // wanted if self.counts and wanted else None


@dataclass(frozen=True)
class Game:
    name: str
    state: str
    vimm: str | None


@dataclass(frozen=True)
class Page:
    games: list[Game]
    total: int
    offset: int
    limit: int


@dataclass(frozen=True)
class InboxFile:
    name: str
    size: int
    partial: bool


@dataclass(frozen=True)
class InboxListing:
    files: list[InboxFile]
    total: int


def platform_views(context: Context, database: state.State) -> list[PlatformView]:
    counts = database.counts()
    return [
        PlatformView(
            slug, platform.dat.split("/", 1)[-1], database.scanned_at(slug), counts.get(slug)
        )
        for slug, platform in context.config.platforms.items()
    ]


def site_code(context: Context, slug: str, site: str) -> str | None:
    registered = context.platforms.get(slug)
    return getattr(registered, site) if registered else None


def platform_view(context: Context, database: state.State, slug: str) -> PlatformView:
    return next(view for view in platform_views(context, database) if view.slug == slug)


def games_page(
    context: Context,
    database: state.State,
    slug: str,
    states: Sequence[str],
    query: str,
    offset: int,
    limit: int = PAGE_SIZE,
) -> Page:
    items, total = database.entries(slug, states, query, limit, offset)
    entry = context.platforms.get(slug)
    return Page([_game(item, entry) for item in items], total, offset, limit)


def _game(item: state.Item, entry: registry.Entry | None) -> Game:
    if item.state != "missing" or entry is None:
        return Game(item.game, item.state, None)
    vimm = links.vimm_search(entry.vimm, item.game) if entry.vimm else None
    return Game(item.game, item.state, vimm)


def page_url(path: str, params: dict[str, str | int], offset: int) -> str:
    kept = {key: value for key, value in params.items() if value != ""}
    return f"{path}?{urlencode({**kept, 'offset': offset})}"


def list_inbox(inbox: Path, limit: int = PAGE_SIZE) -> InboxListing:
    files: list[InboxFile] = []
    total = 0
    for directory, names, filenames in os.walk(inbox):
        if Path(directory) == inbox:
            names[:] = sorted(name for name in names if name not in igir.SET_ASIDE)
        for filename in sorted(filenames):
            if filename in JUNK_NAMES or filename.startswith(JUNK_PREFIX):
                continue
            path = Path(directory) / filename
            size = _size_of(path)
            if size is None:
                continue
            total += 1
            if len(files) < limit:
                files.append(
                    InboxFile(str(path.relative_to(inbox)), size, filename.endswith(PART_SUFFIX))
                )
    return InboxListing(files, total)


def _size_of(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def set_aside_counts(inboxes: Sequence[Path]) -> dict[str, int]:
    return {
        name: sum(len(filenames) for inbox in inboxes for _, _, filenames in os.walk(inbox / name))
        for name in igir.SET_ASIDE
    }


def human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    value = size / 1024
    for unit in ("KB", "MB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def stamp(value: str) -> str:
    return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M UTC")


def duration(started: str, finished: str) -> str:
    seconds = round(
        (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds()
    )
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes} min {seconds} s" if minutes else f"{seconds} s"
