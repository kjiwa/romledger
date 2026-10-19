import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from romledger import http, igir, scan
from romledger.config import Config, ConfigError, Platform
from romledger.sources import SOURCES, consoleroms
from romledger.sources.base import Source, fetch_to
from romledger.sources.errors import FetchError, SourceBlocked, SourceChanged

SourcesFactory = Callable[[Platform, Sequence[str]], list[Source]]
REJECTED_DIRS = (igir.UNMATCHED_DIR, igir.UNWANTED_DIR, igir.DUPLICATES_DIR)


@dataclass
class FetchResult:
    fetched: list[str] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


class _SetAside(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(str(path))
        self.path = path


def build_sources(
    platform: Platform, names: Sequence[str], client: httpx.Client, throttle: http.Throttle
) -> list[Source]:
    builders: dict[str, Callable[[], Source]] = {
        consoleroms.NAME: lambda: consoleroms.ConsoleromsSource(
            platform.consoleroms or "", client, throttle
        ),
    }
    return [builders[name]() for name in names]


def default_sources(platform: Platform) -> list[str]:
    codes = {consoleroms.NAME: platform.consoleroms}
    return [name for name, info in SOURCES.items() if info.fetch and codes.get(name)]


def check_source(name: str) -> None:
    info = SOURCES.get(name)
    if info is None:
        raise ConfigError(f"unknown source {name!r}. Sources: {', '.join(SOURCES)}.")
    if not info.fetch:
        raise ConfigError(
            f"{info.label} cannot be fetched from the command line; "
            "download from it with the browser extension."
        )


def select_sources_or_none(platform: Platform, only: str | None) -> list[str]:
    available = default_sources(platform)
    return available if only is None else [name for name in available if name == only]


def select_sources(slug: str, platform: Platform, only: str | None) -> list[str]:
    available = default_sources(platform)
    if only is None:
        return available
    check_source(only)
    if only not in available:
        raise ConfigError(
            f"no source {only!r} carries {slug}. Sources for {slug}: {', '.join(available)}."
        )
    return [only]


def fetch_platform(
    config: Config,
    slug: str,
    data_dir: Path,
    limit: int | None,
    dry_run: bool,
    sources_factory: SourcesFactory,
    client: httpx.Client,
    throttle: http.Throttle,
    only: str | None = None,
) -> FetchResult:
    games = scan.missing_games(data_dir, slug)
    names = select_sources(slug, config.platforms[slug], only)
    run = _Run(config.library.inboxes, sources_factory(config.platforms[slug], names), dry_run)
    for game in games:
        if not run.sources or (limit is not None and len(run.result.fetched) >= limit):
            break
        run.fetch(game, client, throttle)
    verb = "would fetch" if dry_run else "fetched"
    result = run.result
    print(
        f"{verb} {len(result.fetched)}, not found {len(result.not_found)}, "
        f"failed {len(result.failed)}, skipped {len(result.skipped)}"
    )
    return result


class _Run:
    def __init__(self, inboxes: Sequence[Path], sources: list[Source], dry_run: bool) -> None:
        self.result = FetchResult()
        self._inboxes = inboxes
        self.sources = sources
        self._dry_run = dry_run

    def fetch(self, game: str, client: httpx.Client, throttle: http.Throttle) -> None:
        failure: str | None = None
        set_aside: Path | None = None
        blocked = False
        for source in list(self.sources):
            try:
                if self._attempt(source, game, client, throttle):
                    return
            except SourceBlocked as error:
                self._drop(source, error)
                self.result.blocked.append(str(error))
                blocked = True
            except SourceChanged as error:
                self._drop(source, error)
                failure = str(error)
            except _SetAside as error:
                set_aside = error.path
            except (FetchError, httpx.HTTPError, OSError) as error:
                failure = str(error) or type(error).__name__
        if blocked and failure is None:
            failure = "blocked by robots.txt"
        if failure is not None:
            print(f"failed {game}: {failure}")
            self.result.failed.append((game, failure))
        elif set_aside is not None:
            print(f"skipped {game}: {set_aside} was set aside by an earlier import")
            self.result.skipped.append(game)
        else:
            print(f"not found {game}")
            self.result.not_found.append(game)

    def _attempt(
        self, source: Source, game: str, client: httpx.Client, throttle: http.Throttle
    ) -> bool:
        candidate = source.find(game)
        if candidate is None:
            return False
        self._reject_set_aside(candidate.filename)
        if self._dry_run:
            print(f"would fetch {game} ({source.name})")
        else:
            fetch_to(self._inboxes[0], candidate, client, throttle)
            print(f"fetched {game} ({source.name})")
        self.result.fetched.append(game)
        return True

    def _reject_set_aside(self, filename: str) -> None:
        for inbox in self._inboxes:
            for directory in REJECTED_DIRS:
                if (inbox / directory / filename).exists():
                    raise _SetAside(inbox / directory / filename)

    def _drop(self, source: Source, error: Exception) -> None:
        print(f"romledger: warning: skipping {source.name}: {error}", file=sys.stderr)
        self.sources.remove(source)
