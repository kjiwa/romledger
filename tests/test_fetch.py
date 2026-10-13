from collections.abc import Callable, Sequence
from pathlib import Path

import httpx
import pytest

from romledger import fetch, http, state
from romledger.config import Config, ConfigError, Library, Platform
from romledger.sources import coolrom, internet_archive
from romledger.sources.base import Candidate, Source
from romledger.sources.errors import SourceBlocked, SourceChanged

GAMES = ["Alpha (USA)", "Beta (USA)", "Gamma (USA)"]
BODY = b"rom-bytes"

Outcome = Candidate | Exception | None


class FakeSource:
    def __init__(self, name: str, outcomes: dict[str, Outcome]) -> None:
        self.name = name
        self.outcomes = outcomes
        self.asked: list[str] = []

    def find(self, game: str) -> Candidate | None:
        self.asked.append(game)
        outcome = self.outcomes.get(game)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def found(game: str, path: str = "/rom") -> Candidate:
    return Candidate(game, lambda: f"https://dl.example{path}/{game}", f"{game}.zip")


class Network:
    def __init__(self, failing: Sequence[str] = ()) -> None:
        self.requests: list[str] = []
        self._failing = failing

    def client(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request.url.path)
            if any(name in request.url.path for name in self._failing):
                return httpx.Response(500)
            return httpx.Response(200, content=BODY)

        return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def inbox(tmp_path: Path) -> Path:
    path = tmp_path / "inbox"
    path.mkdir()
    return path


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    path = tmp_path / "data"
    with state.State(path / "state.db") as database:
        items = [state.Item(game, "missing", None) for game in GAMES]
        database.replace_platform("nes", items, [], "v", "t")
    return path


def make_config(inbox: Path) -> Config:
    platform = Platform(dat="no-intro/x", sources=("coolrom", "internet-archive"))
    return Config(Library(inbox.parent / "roms", (inbox,)), {"nes": platform})


def run(
    inbox: Path,
    data_dir: Path,
    sources: list[Source],
    network: Network | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    only: str | None = None,
) -> fetch.FetchResult:
    def factory(platform: Platform, names: Sequence[str]) -> list[Source]:
        return sources

    return fetch.fetch_platform(
        make_config(inbox),
        "nes",
        data_dir,
        limit,
        dry_run,
        factory,
        (network or Network()).client(),
        http.Throttle(0.0),
        only,
    )


def test_fetches_every_missing_game(
    inbox: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = FakeSource("coolrom", {game: found(game) for game in GAMES})
    result = run(inbox, data_dir, [source])
    assert result.fetched == GAMES
    assert sorted(path.name for path in inbox.iterdir()) == [f"{game}.zip" for game in GAMES]
    assert capsys.readouterr().out.splitlines() == [
        "fetched Alpha (USA) (coolrom)",
        "fetched Beta (USA) (coolrom)",
        "fetched Gamma (USA) (coolrom)",
        "fetched 3, not found 0, failed 0",
    ]


def test_limit_stops_after_n_fetches(inbox: Path, data_dir: Path) -> None:
    source = FakeSource("coolrom", {"Beta (USA)": found("Beta (USA)")})
    result = run(inbox, data_dir, [source], limit=1)
    assert result.fetched == ["Beta (USA)"]
    assert result.not_found == ["Alpha (USA)"]
    assert source.asked == ["Alpha (USA)", "Beta (USA)"]


def test_not_found_is_not_a_failure(
    inbox: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = run(inbox, data_dir, [FakeSource("coolrom", {})])
    assert result.not_found == GAMES
    assert result.failed == []
    assert "not found Alpha (USA)" in capsys.readouterr().out


def test_a_failed_game_does_not_stop_the_run(
    inbox: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = FakeSource("coolrom", {game: found(game, "/rom") for game in GAMES})
    result = run(inbox, data_dir, [source], Network(failing=["Beta"]))
    assert result.fetched == ["Alpha (USA)", "Gamma (USA)"]
    assert [game for game, _ in result.failed] == ["Beta (USA)"]
    assert "HTTP 500" in result.failed[0][1]
    assert (
        "failed Beta (USA): https://dl.example/rom/Beta (USA): HTTP 500" in capsys.readouterr().out
    )
    assert not any(path.name.startswith("Beta") for path in inbox.iterdir())


def test_the_next_source_is_tried(inbox: Path, data_dir: Path) -> None:
    first = FakeSource("coolrom", {"Alpha (USA)": httpx.ConnectError("")})
    second = FakeSource("internet-archive", {game: found(game) for game in GAMES})
    result = run(inbox, data_dir, [first, second])
    assert result.fetched == GAMES
    assert result.failed == []


def test_a_failure_survives_a_later_miss(inbox: Path, data_dir: Path) -> None:
    first = FakeSource("coolrom", {"Alpha (USA)": httpx.ReadTimeout("")})
    result = run(inbox, data_dir, [first, FakeSource("internet-archive", {})])
    assert result.failed[0] == ("Alpha (USA)", "ReadTimeout")
    assert result.not_found == ["Beta (USA)", "Gamma (USA)"]


def test_an_unwritable_inbox_fails_each_game(data_dir: Path, tmp_path: Path) -> None:
    source = FakeSource("coolrom", {game: found(game) for game in GAMES})
    result = run(tmp_path / "missing", data_dir, [source])
    assert [game for game, _ in result.failed] == GAMES


def test_source_changed_drops_the_source(
    inbox: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    changed = SourceChanged("https://coolrom.com/x", "no rows")
    broken = FakeSource("coolrom", {"Alpha (USA)": changed})
    backup = FakeSource("internet-archive", {"Beta (USA)": found("Beta (USA)")})
    result = run(inbox, data_dir, [broken, backup])
    assert broken.asked == ["Alpha (USA)"]
    assert result.fetched == ["Beta (USA)"]
    assert [game for game, _ in result.failed] == ["Alpha (USA)"]
    assert "skipping coolrom" in capsys.readouterr().err


def test_source_changed_with_no_source_left_stops_the_run(inbox: Path, data_dir: Path) -> None:
    broken = FakeSource("coolrom", {"Alpha (USA)": SourceChanged("u", "no rows")})
    result = run(inbox, data_dir, [broken])
    assert broken.asked == ["Alpha (USA)"]
    assert len(result.failed) == 1
    assert result.not_found == []


def test_blocked_source_is_skipped(
    inbox: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    blocked = FakeSource("coolrom", {"Alpha (USA)": SourceBlocked("https://c/x", "robots")})
    result = run(inbox, data_dir, [blocked])
    assert result.blocked == ["https://c/x: not fetched, robots"]
    assert result.failed == []
    assert result.not_found == []
    assert blocked.asked == ["Alpha (USA)"]
    assert "https://c/x: not fetched, robots" in capsys.readouterr().err


def test_dry_run_downloads_nothing(
    inbox: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    network = Network()
    source = FakeSource("coolrom", {"Alpha (USA)": found("Alpha (USA)")})
    result = run(inbox, data_dir, [source], network, dry_run=True)
    assert result.fetched == ["Alpha (USA)"]
    assert network.requests == []
    assert list(inbox.iterdir()) == []
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "would fetch Alpha (USA) (coolrom)"
    assert out[-1] == "would fetch 1, not found 2, failed 0"


def test_dry_run_with_coolrom_requests_only_section_pages(
    inbox: Path, data_dir: Path, fixtures: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with state.State(data_dir / "state.db") as database:
        database.replace_platform(
            "nes", [state.Item("Saint Sword (USA)", "missing", None)], [], "v", "t"
        )
    section = (fixtures / "coolrom" / "section.html").read_text()
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        text = section if request.url.path == "/roms/genesis/s/" else "User-agent: *\n"
        return httpx.Response(200, text=text)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    throttle = http.Throttle(sleep=lambda _: None)

    def factory(platform: Platform, names: Sequence[str]) -> list[Source]:
        return [coolrom.CoolromSource("genesis", client, throttle)]

    result = fetch.fetch_platform(
        make_config(inbox), "nes", data_dir, None, True, factory, client, throttle
    )
    assert result.fetched == ["Saint Sword (USA)"]
    assert requests == ["/robots.txt", "/roms/genesis/s/"]
    assert "would fetch Saint Sword (USA) (coolrom)" in capsys.readouterr().out


def test_unscanned_platform(inbox: Path, tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"not been scanned\. run: romledger scan"):
        run(inbox, tmp_path / "empty", [])


def test_only_restricts_to_one_configured_source(inbox: Path, data_dir: Path) -> None:
    asked: list[Sequence[str]] = []

    def factory(platform: Platform, names: Sequence[str]) -> list[Source]:
        asked.append(names)
        return []

    fetch.fetch_platform(
        make_config(inbox),
        "nes",
        data_dir,
        None,
        True,
        factory,
        Network().client(),
        http.Throttle(0.0),
        "internet-archive",
    )
    assert asked == [["internet-archive"]]


def test_only_must_be_configured(inbox: Path, data_dir: Path) -> None:
    config = make_config(inbox)
    platform = Platform(dat="x", sources=("coolrom",))
    with pytest.raises(ConfigError, match="nes does not list source 'internet-archive'"):
        fetch.select_sources("nes", platform, "internet-archive")
    assert fetch.select_sources("nes", config.platforms["nes"], None) == [
        "coolrom",
        "internet-archive",
    ]


def test_build_sources_in_order() -> None:
    platform = Platform(
        dat="x", sources=("internet-archive", "coolrom"), archive_item="item", coolrom="nes"
    )
    builder: Callable[..., list[Source]] = fetch.build_sources
    built = builder(platform, platform.sources, httpx.Client(), http.Throttle())
    assert [type(source) for source in built] == [
        internet_archive.InternetArchiveSource,
        coolrom.CoolromSource,
    ]
    assert [source.name for source in built] == ["internet-archive", "coolrom"]
