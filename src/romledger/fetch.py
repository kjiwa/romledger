import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from romledger import http, scan
from romledger.config import Config, ConfigError, Platform
from romledger.sources import coolrom, internet_archive
from romledger.sources.base import Source, fetch_to
from romledger.sources.errors import FetchError, SourceBlocked, SourceChanged

SourcesFactory = Callable[[Platform, Sequence[str]], list[Source]]


@dataclass
class FetchResult:
    fetched: list[str] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)


def build_sources(
    platform: Platform, names: Sequence[str], client: httpx.Client, throttle: http.Throttle
) -> list[Source]:
    builders: dict[str, Callable[[], Source]] = {
        coolrom.NAME: lambda: coolrom.CoolromSource(platform.coolrom or "", client, throttle),
        internet_archive.NAME: lambda: internet_archive.InternetArchiveSource(
            platform.archive_item or "", client, throttle
        ),
    }
    return [builders[name]() for name in names]


def select_sources(slug: str, platform: Platform, only: str | None) -> list[str]:
    if only is None:
        return list(platform.sources)
    if only not in platform.sources:
        raise ConfigError(
            f"{slug} does not list source {only!r}. "
            f"Configured sources: {', '.join(platform.sources)}."
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
    run = _Run(config.library.inboxes[0], sources_factory(config.platforms[slug], names), dry_run)
    for game in games:
        if not run.sources or (limit is not None and len(run.result.fetched) >= limit):
            break
        run.fetch(game, client, throttle)
    verb = "would fetch" if dry_run else "fetched"
    result = run.result
    print(
        f"{verb} {len(result.fetched)}, not found {len(result.not_found)}, "
        f"failed {len(result.failed)}"
    )
    return result


class _Run:
    def __init__(self, inbox: Path, sources: list[Source], dry_run: bool) -> None:
        self.result = FetchResult()
        self._inbox = inbox
        self.sources = sources
        self._dry_run = dry_run

    def fetch(self, game: str, client: httpx.Client, throttle: http.Throttle) -> None:
        failure: str | None = None
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
            except (FetchError, httpx.HTTPError, OSError) as error:
                failure = str(error) or type(error).__name__
        if blocked and failure is None:
            failure = "blocked by robots.txt"
        if failure is not None:
            print(f"failed {game}: {failure}")
            self.result.failed.append((game, failure))
        else:
            print(f"not found {game}")
            self.result.not_found.append(game)

    def _attempt(
        self, source: Source, game: str, client: httpx.Client, throttle: http.Throttle
    ) -> bool:
        candidate = source.find(game)
        if candidate is None:
            return False
        if self._dry_run:
            print(f"would fetch {game} ({source.name})")
        else:
            fetch_to(self._inbox, candidate, client, throttle)
            print(f"fetched {game} ({source.name})")
        self.result.fetched.append(game)
        return True

    def _drop(self, source: Source, error: Exception) -> None:
        print(f"romledger: warning: skipping {source.name}: {error}", file=sys.stderr)
        self.sources.remove(source)
