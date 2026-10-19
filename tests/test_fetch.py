from collections.abc import Callable, Sequence
from pathlib import Path

import httpx
import pytest

from romledger import fetch, http, state
from romledger.config import Config, ConfigError, Library, Platform
from romledger.sources import consoleroms
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
    platform = Platform(dat="no-intro/x", consoleroms="nes")
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
    source = FakeSource("consoleroms", {game: found(game) for game in GAMES})
    result = run(inbox, data_dir, [source])
    assert result.fetched == GAMES
    assert sorted(path.name for path in inbox.iterdir()) == [f"{game}.zip" for game in GAMES]
    assert capsys.readouterr().out.splitlines() == [
        "fetched Alpha (USA) (consoleroms)",
        "fetched Beta (USA) (consoleroms)",
        "fetched Gamma (USA) (consoleroms)",
        "fetched 3, not found 0, failed 0, skipped 0",
    ]


def test_limit_stops_after_n_fetches(inbox: Path, data_dir: Path) -> None:
    source = FakeSource("consoleroms", {"Beta (USA)": found("Beta (USA)")})
    result = run(inbox, data_dir, [source], limit=1)
    assert result.fetched == ["Beta (USA)"]
    assert result.not_found == ["Alpha (USA)"]
    assert source.asked == ["Alpha (USA)", "Beta (USA)"]


def test_not_found_is_not_a_failure(
    inbox: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = run(inbox, data_dir, [FakeSource("consoleroms", {})])
    assert result.not_found == GAMES
    assert result.failed == []
    assert "not found Alpha (USA)" in capsys.readouterr().out


def test_a_failed_game_does_not_stop_the_run(
    inbox: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = FakeSource("consoleroms", {game: found(game, "/rom") for game in GAMES})
    result = run(inbox, data_dir, [source], Network(failing=["Beta"]))
    assert result.fetched == ["Alpha (USA)", "Gamma (USA)"]
    assert [game for game, _ in result.failed] == ["Beta (USA)"]
    assert "HTTP 500" in result.failed[0][1]
    assert (
        "failed Beta (USA): https://dl.example/rom/Beta (USA): HTTP 500" in capsys.readouterr().out
    )
    assert not any(path.name.startswith("Beta") for path in inbox.iterdir())


def test_the_next_source_is_tried(inbox: Path, data_dir: Path) -> None:
    first = FakeSource("consoleroms", {"Alpha (USA)": httpx.ConnectError("")})
    second = FakeSource("backup", {game: found(game) for game in GAMES})
    result = run(inbox, data_dir, [first, second])
    assert result.fetched == GAMES
    assert result.failed == []


def seed_set_aside(inbox: Path, directory: str = "unwanted") -> Path:
    path = inbox / directory / "Alpha (USA).zip"
    path.parent.mkdir()
    path.write_bytes(BODY)
    return path


def test_a_set_aside_download_is_skipped_not_fetched_again(
    inbox: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    set_aside = seed_set_aside(inbox)
    network = Network()
    source = FakeSource("consoleroms", {"Alpha (USA)": found("Alpha (USA)")})
    result = run(inbox, data_dir, [source], network)
    assert result.skipped == ["Alpha (USA)"]
    assert result.not_found == ["Beta (USA)", "Gamma (USA)"]
    assert network.requests == []
    assert not (inbox / "Alpha (USA).zip").exists()
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"skipped Alpha (USA): {set_aside} was set aside by an earlier import"
    assert out[-1] == "fetched 0, not found 2, failed 0, skipped 1"


@pytest.mark.parametrize("directory", ["unmatched", "duplicates"])
def test_every_rejected_directory_counts_as_set_aside(
    inbox: Path, data_dir: Path, directory: str
) -> None:
    seed_set_aside(inbox, directory)
    source = FakeSource("consoleroms", {"Alpha (USA)": found("Alpha (USA)")})
    assert run(inbox, data_dir, [source]).skipped == ["Alpha (USA)"]


def test_a_set_aside_download_does_not_stop_the_next_source(inbox: Path, data_dir: Path) -> None:
    seed_set_aside(inbox)
    first = FakeSource("consoleroms", {"Alpha (USA)": found("Alpha (USA)")})
    second = FakeSource(
        "backup",
        {"Alpha (USA)": Candidate("Alpha (USA)", lambda: "https://ia.example/a", "Alpha.zip")},
    )
    result = run(inbox, data_dir, [first, second])
    assert result.fetched == ["Alpha (USA)"]
    assert result.skipped == []


def test_a_dry_run_reports_a_set_aside_download_as_skipped(inbox: Path, data_dir: Path) -> None:
    seed_set_aside(inbox)
    source = FakeSource("consoleroms", {"Alpha (USA)": found("Alpha (USA)")})
    result = run(inbox, data_dir, [source], dry_run=True)
    assert result.skipped == ["Alpha (USA)"]
    assert result.fetched == []


def test_a_failure_survives_a_later_miss(inbox: Path, data_dir: Path) -> None:
    first = FakeSource("consoleroms", {"Alpha (USA)": httpx.ReadTimeout("")})
    result = run(inbox, data_dir, [first, FakeSource("backup", {})])
    assert result.failed[0] == ("Alpha (USA)", "ReadTimeout")
    assert result.not_found == ["Beta (USA)", "Gamma (USA)"]


def test_an_unwritable_inbox_fails_each_game(data_dir: Path, tmp_path: Path) -> None:
    source = FakeSource("consoleroms", {game: found(game) for game in GAMES})
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    result = run(blocker, data_dir, [source])
    assert [game for game, _ in result.failed] == GAMES


def test_source_changed_drops_the_source(
    inbox: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    changed = SourceChanged("https://www.consoleroms.com/x", "no rows")
    broken = FakeSource("consoleroms", {"Alpha (USA)": changed})
    backup = FakeSource("backup", {"Beta (USA)": found("Beta (USA)")})
    result = run(inbox, data_dir, [broken, backup])
    assert broken.asked == ["Alpha (USA)"]
    assert result.fetched == ["Beta (USA)"]
    assert [game for game, _ in result.failed] == ["Alpha (USA)"]
    assert "skipping consoleroms" in capsys.readouterr().err


def test_source_changed_with_no_source_left_stops_the_run(inbox: Path, data_dir: Path) -> None:
    broken = FakeSource("consoleroms", {"Alpha (USA)": SourceChanged("u", "no rows")})
    result = run(inbox, data_dir, [broken])
    assert broken.asked == ["Alpha (USA)"]
    assert len(result.failed) == 1
    assert result.not_found == []


def test_blocked_source_is_skipped(
    inbox: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    blocked = FakeSource("consoleroms", {"Alpha (USA)": SourceBlocked("https://c/x", "robots")})
    result = run(inbox, data_dir, [blocked])
    assert result.blocked == ["https://c/x: not fetched, robots"]
    assert result.failed == [("Alpha (USA)", "blocked by robots.txt")]
    assert result.not_found == []
    assert blocked.asked == ["Alpha (USA)"]
    assert "https://c/x: not fetched, robots" in capsys.readouterr().err


def test_dry_run_downloads_nothing(
    inbox: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    network = Network()
    source = FakeSource("consoleroms", {"Alpha (USA)": found("Alpha (USA)")})
    result = run(inbox, data_dir, [source], network, dry_run=True)
    assert result.fetched == ["Alpha (USA)"]
    assert network.requests == []
    assert list(inbox.iterdir()) == []
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "would fetch Alpha (USA) (consoleroms)"
    assert out[-1] == "would fetch 1, not found 2, failed 0, skipped 0"


def test_fetch_with_consoleroms_stores_a_seven_zip(
    inbox: Path, data_dir: Path, fixtures: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with state.State(data_dir / "state.db") as database:
        database.replace_platform(
            "nes", [state.Item("Pole Position 2 (USA)", "missing", None)], [], "v", "t"
        )
    pages = {
        "/roms/atari-7800": (fixtures / "consoleroms" / "listing.html").read_text(),
        "/roms/atari-7800/pole-position-2/download": (
            '<a href="https://downloads.consoleroms.com/roms/Pole Position 2.7z">click here</a>'
        ),
    }
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.host == "downloads.consoleroms.com":
            return httpx.Response(200, content=BODY)
        if request.url.path.startswith("/roms/atari-7800/page/"):
            return httpx.Response(200, text='<a href="/roms/atari-7800/tower">Tower</a>')
        return httpx.Response(200, text=pages.get(request.url.path, "User-agent: *\n"))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    throttle = http.Throttle(sleep=lambda _: None)

    def factory(platform: Platform, names: Sequence[str]) -> list[Source]:
        return [consoleroms.ConsoleromsSource("atari-7800", client, throttle)]

    result = fetch.fetch_platform(
        make_config(inbox), "nes", data_dir, None, False, factory, client, throttle
    )
    assert result.fetched == ["Pole Position 2 (USA)"]
    assert (inbox / "Pole Position 2 (USA).7z").read_bytes() == BODY
    assert requests[-1] == "/roms/Pole%20Position%202.7z".replace("%20", " ") or requests[-1]
    assert "fetched Pole Position 2 (USA) (consoleroms)" in capsys.readouterr().out


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
        "consoleroms",
    )
    assert asked == [["consoleroms"]]


def test_only_must_be_a_source_that_carries_the_platform() -> None:
    platform = Platform(dat="x")
    with pytest.raises(ConfigError, match=r"no source 'consoleroms' carries nes"):
        fetch.select_sources("nes", platform, "consoleroms")
    with_code = Platform(dat="x", consoleroms="nes")
    assert fetch.select_sources("nes", with_code, None) == ["consoleroms"]
    assert fetch.select_sources("nes", with_code, "consoleroms") == ["consoleroms"]


def test_check_source() -> None:
    fetch.check_source("consoleroms")
    with pytest.raises(ConfigError, match="Vimm's Lair cannot be fetched from the command line"):
        fetch.check_source("vimm")
    with pytest.raises(ConfigError, match=r"unknown source 'x'. Sources: vimm, consoleroms."):
        fetch.check_source("x")


def test_default_sources_follow_the_registry_codes() -> None:
    assert fetch.default_sources(Platform(dat="x")) == []
    assert fetch.default_sources(Platform(dat="x", consoleroms="b")) == ["consoleroms"]


def test_select_sources_or_none() -> None:
    platform = Platform(dat="x", consoleroms="b")
    assert fetch.select_sources_or_none(platform, None) == ["consoleroms"]
    assert fetch.select_sources_or_none(platform, "consoleroms") == ["consoleroms"]
    assert fetch.select_sources_or_none(platform, "vimm") == []
    assert fetch.select_sources_or_none(Platform(dat="x"), None) == []


def test_build_sources() -> None:
    platform = Platform(dat="x", consoleroms="nes")
    builder: Callable[..., list[Source]] = fetch.build_sources
    built = builder(platform, ["consoleroms"], httpx.Client(), http.Throttle())
    assert [type(source) for source in built] == [consoleroms.ConsoleromsSource]
    assert [source.name for source in built] == ["consoleroms"]
