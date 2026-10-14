from pathlib import Path

import httpx
import pytest

from conftest import FakeThrottle
from romledger import http
from romledger.sources import consoleroms
from romledger.sources.errors import FetchError, SourceBlocked, SourceChanged

LISTING_URL = "https://www.consoleroms.com/roms/atari-7800"
DOWNLOAD_URL = "https://www.consoleroms.com/roms/atari-7800/pole-position-2/download"
HEADER = '<a itemprop="item" href="/roms/atari-7800"><span>Atari 7800</span></a>'


def card(slug: str, title: str) -> str:
    return (
        f'<div><a href="/roms/atari-7800/{slug}"><img alt="{title}"></a>'
        f'<a href="/roms/atari-7800/{slug}" class="btn btn-primary" role="button">View</a>'
        f'<strong><a href="/roms/atari-7800/{slug}">{title}</a></strong></div>'
    )


def listing(*pairs: tuple[str, str]) -> str:
    return HEADER + "".join(card(slug, title) for slug, title in pairs)


def download(link: str) -> str:
    return f'<p>please <a href="{link}" rel="nofollow">click here</a>.</p>'


class Site:
    def __init__(self, fixtures: Path, robots: str = "User-agent: *\nDisallow:\n") -> None:
        self.requests: list[str] = []
        self.pages = {
            "/robots.txt": httpx.Response(200, text=robots),
            "/roms/atari-7800": httpx.Response(
                200, text=(fixtures / "consoleroms" / "listing.html").read_text()
            ),
            "/roms/atari-7800/page/2": httpx.Response(200, text=listing(("joust", "Joust"))),
            "/roms/atari-7800/page/3": httpx.Response(
                200, text=listing(("joust", "Joust"), ("tower-toppler", "Tower Toppler"))
            ),
            "/roms/atari-7800/page/4": httpx.Response(
                200, text=listing(("xenophobe", "Xenophobe"))
            ),
            "/roms/atari-7800/pole-position-2/download": httpx.Response(
                200, text=(fixtures / "consoleroms" / "download.html").read_text()
            ),
        }

    def client(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request.url.raw_path.decode())
            return self.pages.get(request.url.path, httpx.Response(404))

        return httpx.Client(transport=httpx.MockTransport(handler))

    def source(self, throttle: http.Throttle) -> consoleroms.ConsoleromsSource:
        return consoleroms.ConsoleromsSource("atari-7800", self.client(), throttle)


@pytest.fixture
def site(fixtures: Path) -> Site:
    return Site(fixtures)


@pytest.fixture
def throttle(fake_throttle: FakeThrottle) -> http.Throttle:
    return fake_throttle(0.0)[0]


def test_parse_listing_fixture(fixtures: Path) -> None:
    html = (fixtures / "consoleroms" / "listing.html").read_text()
    rows, pages = consoleroms.parse_listing(html, "atari-7800", LISTING_URL)
    assert rows == [
        consoleroms.Row("pole-position-2", "Pole Position 2"),
        consoleroms.Row("galaga", "Galaga"),
        consoleroms.Row("centipede", "Centipede"),
    ]
    assert pages == 4


def test_parse_listing_without_pagination_is_one_page() -> None:
    assert consoleroms.parse_listing(listing(("a", "A")), "atari-7800", LISTING_URL)[1] == 1


def test_parse_listing_accepts_single_quoted_hrefs() -> None:
    html = (
        HEADER
        + "<a href='/roms/atari-7800/joust'>Joust</a>"
        + "<a class='page-link' href='/roms/atari-7800/page/7'>7</a>"
    )
    assert consoleroms.parse_listing(html, "atari-7800", LISTING_URL) == (
        [consoleroms.Row("joust", "Joust")],
        7,
    )


def test_parse_listing_ignores_buttons_other_platforms_and_repeats() -> None:
    html = (
        HEADER
        + card("joust", "Joust")
        + card("joust", "Joust Again")
        + '<a href="/roms/atari-7800" class="btn" role="button">Atari 7800</a>'
        + '<a href="/roms/nes/zelda">Zelda</a>'
        + '<a href="/roms/atari-7800/tower/download">Tower</a>'
    )
    rows, _ = consoleroms.parse_listing(html, "atari-7800", LISTING_URL)
    assert rows == [consoleroms.Row("joust", "Joust")]


@pytest.mark.parametrize("html", ["", "<html><body>Maintenance</body></html>", HEADER])
def test_parse_listing_unrecognized_page_is_source_changed(html: str) -> None:
    with pytest.raises(SourceChanged, match="no game rows"):
        consoleroms.parse_listing(html, "atari-7800", LISTING_URL)


def test_parse_download_link_fixture_encodes_spaces(fixtures: Path) -> None:
    html = (fixtures / "consoleroms" / "download.html").read_text()
    assert (
        consoleroms.parse_download_link(html, DOWNLOAD_URL)
        == "https://downloads.consoleroms.com/roms/Pole%20Position%202.zip"
    )


def test_parse_download_link_keeps_encoded_names_stable() -> None:
    link = "https://downloads.consoleroms.com/roms/Pole%20Position%202.7z"
    assert consoleroms.parse_download_link(download(link), DOWNLOAD_URL) == link


@pytest.mark.parametrize(
    ("html", "message"),
    [
        ("<html></html>", "no download link"),
        (download("https://elsewhere.example/roms/A.zip"), "no download link"),
        (download("https://downloads.consoleroms.com/roms/A.exe"), "unexpected download file"),
    ],
)
def test_parse_download_link_unrecognized_is_source_changed(html: str, message: str) -> None:
    with pytest.raises(SourceChanged, match=message):
        consoleroms.parse_download_link(html, DOWNLOAD_URL)


def test_pick_unique_match_ignores_region() -> None:
    rows = [consoleroms.Row("a", "Joust"), consoleroms.Row("b", "Galaga")]
    assert consoleroms.pick(rows, "Joust (USA)") == rows[0]


def test_pick_without_a_match_is_none() -> None:
    assert consoleroms.pick([consoleroms.Row("a", "Joust")], "Galaga (USA)") is None


def test_pick_ambiguous_warns_and_is_none(capsys: pytest.CaptureFixture[str]) -> None:
    rows = [consoleroms.Row("a", "Joust"), consoleroms.Row("b", "Joust (Beta)")]
    assert consoleroms.pick(rows, "Joust (USA)") is None
    assert "ambiguous: Joust (USA) matches 2 ConsoleRoms rows" in capsys.readouterr().err


def test_pick_never_matches_titles_that_normalize_to_nothing() -> None:
    row = consoleroms.Row("a", "ゲーム")
    assert consoleroms.pick([row], "ゲーム (Japan)") is None


def test_find_returns_a_candidate_with_the_real_suffix(site: Site, throttle: http.Throttle) -> None:
    candidate = site.source(throttle).find("Pole Position 2 (USA)")
    assert candidate is not None
    assert candidate.game == "Pole Position 2 (USA)"
    assert candidate.filename == "Pole Position 2 (USA).zip"
    assert (
        candidate.url_resolver() == "https://downloads.consoleroms.com/roms/Pole%20Position%202.zip"
    )
    assert site.requests[-1] == "/roms/atari-7800/pole-position-2/download"


def test_find_keeps_the_seven_zip_suffix(site: Site, throttle: http.Throttle) -> None:
    site.pages["/roms/atari-7800/pole-position-2/download"] = httpx.Response(
        200, text=download("https://downloads.consoleroms.com/roms/Pole Position 2.7z")
    )
    candidate = site.source(throttle).find("Pole Position 2 (USA)")
    assert candidate is not None
    assert candidate.filename == "Pole Position 2 (USA).7z"


def test_find_loads_every_listing_page_once(site: Site, throttle: http.Throttle) -> None:
    source = site.source(throttle)
    assert source.find("Missing One (USA)") is None
    assert source.find("Missing Two (USA)") is None
    assert site.requests == [
        "/robots.txt",
        "/roms/atari-7800",
        "/roms/atari-7800/page/2",
        "/roms/atari-7800/page/3",
        "/roms/atari-7800/page/4",
    ]


def test_find_dedupes_rows_repeated_across_pages(
    site: Site, throttle: http.Throttle, capsys: pytest.CaptureFixture[str]
) -> None:
    site.pages["/roms/atari-7800/joust/download"] = httpx.Response(
        200, text=download("https://downloads.consoleroms.com/roms/Joust.zip")
    )
    assert site.source(throttle).find("Joust (USA)") is not None
    assert capsys.readouterr().err == ""


def test_find_unknown_game_requests_no_download_page(site: Site, throttle: http.Throttle) -> None:
    assert site.source(throttle).find("Sonic the Hedgehog (USA)") is None
    assert not any(request.endswith("/download") for request in site.requests)


def test_changed_listing_is_source_changed(site: Site, throttle: http.Throttle) -> None:
    site.pages["/roms/atari-7800"] = httpx.Response(200, text="<html>new design</html>")
    with pytest.raises(SourceChanged):
        site.source(throttle).find("Joust (USA)")


def test_changed_download_page_is_source_changed(site: Site, throttle: http.Throttle) -> None:
    site.pages["/roms/atari-7800/pole-position-2/download"] = httpx.Response(200, text="<html>")
    with pytest.raises(SourceChanged, match="no download link"):
        site.source(throttle).find("Pole Position 2 (USA)")


def test_server_error_is_a_fetch_error(site: Site, throttle: http.Throttle) -> None:
    site.pages["/roms/atari-7800"] = httpx.Response(503)
    with pytest.raises(FetchError, match="HTTP 503"):
        site.source(throttle).find("Joust (USA)")


def test_robots_disallow_blocks_the_source(fixtures: Path, throttle: http.Throttle) -> None:
    blocked = Site(fixtures, "User-agent: *\nDisallow: /roms/\n")
    with pytest.raises(SourceBlocked, match=r"https://www\.consoleroms\.com/roms/atari-7800"):
        blocked.source(throttle).find("Joust (USA)")
    assert blocked.requests == ["/robots.txt"]


def test_requests_are_spaced_at_least_one_second(
    fixtures: Path, fake_throttle: FakeThrottle
) -> None:
    throttle, sleeps = fake_throttle(0.0)
    assert Site(fixtures).source(throttle).find("Pole Position 2 (USA)") is not None
    assert sleeps == [1.0] * 5


@pytest.mark.live
def test_live_listing_and_download_page() -> None:
    with http.client() as client:
        source = consoleroms.ConsoleromsSource("atari-7800", client, http.Throttle())
        candidate = source.find("Pole Position 2 (USA)")
    assert candidate is not None
    assert candidate.filename == "Pole Position 2 (USA).zip"
