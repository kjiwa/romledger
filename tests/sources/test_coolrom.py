import json
from pathlib import Path

import httpx
import pytest

from conftest import FakeThrottle
from romledger import http
from romledger.sources import coolrom
from romledger.sources.errors import FetchError, SourceBlocked, SourceChanged

SECTION_URL = "https://coolrom.com/roms/genesis/s/"


def rows(*pairs: tuple[str, str]) -> str:
    items = "".join(
        f'<div class="{region}"><a href="/roms/genesis/{number}/{number}.php">{title}</a>'
        "<br /></div>"
        for number, (region, title) in enumerate(pairs, start=1)
    )
    return f'<div class="header"><a href="/roms/genesis/">Sega Genesis</a></div>{items}'


class Site:
    def __init__(self, fixtures: Path, robots: str = "User-agent: *\nCrawl-delay: 10\n") -> None:
        self.requests: list[str] = []
        self.pages = {
            "/robots.txt": httpx.Response(200, text=robots),
            "/roms/genesis/s/": httpx.Response(
                200, text=(fixtures / "coolrom" / "section.html").read_text()
            ),
            "/dlpop.php": httpx.Response(
                200, text=(fixtures / "coolrom" / "dlpop.html").read_text()
            ),
        }

    def client(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request.url.raw_path.decode())
            return self.pages.get(request.url.path, httpx.Response(404))

        return httpx.Client(transport=httpx.MockTransport(handler))

    def source(self, throttle: http.Throttle) -> coolrom.CoolromSource:
        return coolrom.CoolromSource("genesis", self.client(), throttle)


@pytest.fixture
def site(fixtures: Path) -> Site:
    return Site(fixtures)


@pytest.fixture
def throttle(fake_throttle: FakeThrottle) -> http.Throttle:
    return fake_throttle(0.0)[0]


def test_parse_section_fixture(fixtures: Path) -> None:
    html = (fixtures / "coolrom" / "section.html").read_text()
    parsed = coolrom.parse_section(html, "genesis", SECTION_URL)
    assert [(row.id, row.title, row.region) for row in parsed] == [
        ("6013", "Sagaia", "USA"),
        ("1235", "Saint Sword", "USA"),
        ("47761", "Saint Sword (Japan)", "Japan"),
        ("1308", "Samurai Shodown", "USA"),
        ("47990", "Samurai Shodown (Europe)", "Europe"),
        ("6369", "Saturday Night Slammasters", "USA"),
        ("47772", "Saturday Night Slammasters (Europe)", "Europe"),
        ("48023", "Senjou no Ookami II ~ Mercs (World)", "USA"),
    ]


def test_parse_section_ignores_other_platforms_and_featured_links() -> None:
    html = (
        '<div class="header"><a href="/roms/genesis/">G</a></div>'
        '<table><td><a href="/roms/genesis/1/A.php">A</a></td></table>'
        '<div class="USA"><a href="/roms/snes/2/B.php">B</a></div>'
        '<div><a href="/roms/genesis/3/C.php">C</a></div>'
        "</div></div></div>"
        '<div class="USA"><a href="/roms/genesis/4/D.php">D</a></div>'
    )
    assert [row.id for row in coolrom.parse_section(html, "genesis", SECTION_URL)] == ["4"]


def test_parse_section_without_rows_but_with_header_is_empty() -> None:
    html = '<div class="header"><a href="/roms/genesis/">Sega Genesis</a></div>'
    assert coolrom.parse_section(html, "genesis", SECTION_URL) == []


@pytest.mark.parametrize("html", ["", "<html><body>Maintenance</body></html>"])
def test_parse_section_unrecognized_page_is_source_changed(html: str) -> None:
    with pytest.raises(SourceChanged, match="no game rows or breadcrumb"):
        coolrom.parse_section(html, "genesis", SECTION_URL)


def test_parse_signed_link_fixture(fixtures: Path) -> None:
    html = (fixtures / "coolrom" / "dlpop.html").read_text()
    link = coolrom.parse_signed_link(html, "https://coolrom.com/dlpop.php?id=1")
    assert link.startswith("https://dl.coolrom.com/roms/atari7800/Xenophobe.zip/")
    assert link.endswith("/")


@pytest.mark.parametrize(
    "html",
    [
        "<html></html>",
        '<script>document.getElementById("dl").innerHTML = "wait 5 seconds";</script>',
    ],
)
def test_parse_signed_link_missing_is_source_changed(html: str) -> None:
    with pytest.raises(SourceChanged, match="no download link"):
        coolrom.parse_signed_link(html, "https://coolrom.com/dlpop.php?id=1")


def test_parse_signed_link_with_a_non_json_script_is_source_changed() -> None:
    html = 'document.getElementById("dl").innerHTML = "<a href=\\x22u\\x22>";'
    with pytest.raises(SourceChanged, match="not a JSON string"):
        coolrom.parse_signed_link(html, "https://coolrom.com/dlpop.php?id=1")


def test_parse_signed_link_handles_escaped_quotes() -> None:
    html = (
        'document.getElementById("dl").innerHTML = '
        + json.dumps('<a href="https://dl.coolrom.com/roms/x/A.zip/sig/1/">go</a>')
        + ";"
    )
    assert coolrom.parse_signed_link(html, "u") == "https://dl.coolrom.com/roms/x/A.zip/sig/1/"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Saint Sword (Japan)", "saintsword"),
        ("Saint Sword", "saintsword"),
        ("Pokémon: Red (USA) (Rev 1)", "pokemonred"),
        ("SAME! Same! Same!", "samesamesame"),
    ],
)
def test_normalize(title: str, expected: str) -> None:
    assert coolrom.normalize(title) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Sagaia (USA)", "s"),
        ("'89 Dennou", "0"),
        ("... Zero", "z"),
        ("(!) ", None),
        ("Éclair", "e"),
    ],
)
def test_letter_of(title: str, expected: str | None) -> None:
    assert coolrom.letter_of(title) == expected


@pytest.mark.parametrize(
    ("game", "expected"),
    [
        ("Alpha (USA) (Rev 1)", "usa"),
        ("Alpha (USA, Europe)", "usa"),
        ("Alpha (World)", "usa"),
        ("Alpha (Japan)", "japan"),
        ("Alpha", None),
    ],
)
def test_region_of(game: str, expected: str | None) -> None:
    assert coolrom.region_of(game) == expected


def test_find_prefers_the_region_row(site: Site, throttle: http.Throttle) -> None:
    source = site.source(throttle)
    candidate = source.find("Saint Sword (Japan)")
    assert candidate is not None
    assert candidate.filename == "Saint Sword (Japan).zip"
    assert candidate.game == "Saint Sword (Japan)"
    link = candidate.url_resolver()
    assert link.startswith("https://dl.coolrom.com/")
    assert site.requests[-1] == "/dlpop.php?id=47761"


def test_find_world_matches_usa(site: Site, throttle: http.Throttle) -> None:
    candidate = site.source(throttle).find("Senjou no Ookami II ~ Mercs (World)")
    assert candidate is not None
    candidate.url_resolver()
    assert site.requests[-1] == "/dlpop.php?id=48023"


def test_find_falls_back_to_the_unique_row(site: Site, throttle: http.Throttle) -> None:
    candidate = site.source(throttle).find("Senjou no Ookami II ~ Mercs (Europe)")
    assert candidate is not None
    candidate.url_resolver()
    assert site.requests[-1] == "/dlpop.php?id=48023"


def test_find_without_a_preferred_region_among_several_rows_is_ambiguous(
    site: Site, throttle: http.Throttle
) -> None:
    assert site.source(throttle).find("Samurai Shodown (Brazil)") is None


def test_find_unknown_game(site: Site, throttle: http.Throttle) -> None:
    assert site.source(throttle).find("Sonic the Hedgehog (USA)") is None


def test_find_game_without_letter(site: Site, throttle: http.Throttle) -> None:
    assert site.source(throttle).find("(!)") is None
    assert site.requests == []


def test_find_caches_section_pages(site: Site, throttle: http.Throttle) -> None:
    source = site.source(throttle)
    source.find("Saint Sword (USA)")
    source.find("Samurai Shodown (USA)")
    assert site.requests == ["/robots.txt", "/roms/genesis/s/"]


def test_find_never_requests_the_download_page(site: Site, throttle: http.Throttle) -> None:
    source = site.source(throttle)
    assert source.find("Saint Sword (USA)") is not None
    assert not any("dlpop" in request for request in site.requests)


def test_ambiguous_rows_are_skipped_and_logged(
    site: Site, throttle: http.Throttle, capsys: pytest.CaptureFixture[str]
) -> None:
    site.pages["/roms/genesis/s/"] = httpx.Response(
        200, text=rows(("USA", "Sonic"), ("USA", "Sonic (Beta)"), ("Japan", "Sonic (Japan)"))
    )
    source = site.source(throttle)
    assert source.find("Sonic (USA)") is None
    assert "ambiguous: Sonic (USA) matches 2 CoolROM rows" in capsys.readouterr().err
    assert source.find("Sonic (Japan)") is not None
    assert source.find("Sonic (Europe)") is None


def test_missing_section_page_is_not_an_error(site: Site, throttle: http.Throttle) -> None:
    site.pages["/roms/genesis/s/"] = httpx.Response(404)
    assert site.source(throttle).find("Saint Sword (USA)") is None


def test_changed_section_page_is_source_changed(site: Site, throttle: http.Throttle) -> None:
    site.pages["/roms/genesis/s/"] = httpx.Response(200, text="<html>new design</html>")
    with pytest.raises(SourceChanged):
        site.source(throttle).find("Saint Sword (USA)")


def test_server_error_is_a_fetch_error(site: Site, throttle: http.Throttle) -> None:
    site.pages["/roms/genesis/s/"] = httpx.Response(503)
    with pytest.raises(FetchError, match="HTTP 503"):
        site.source(throttle).find("Saint Sword (USA)")


def test_changed_download_page_is_source_changed(site: Site, throttle: http.Throttle) -> None:
    site.pages["/dlpop.php"] = httpx.Response(200, text="<html></html>")
    candidate = site.source(throttle).find("Saint Sword (USA)")
    assert candidate is not None
    with pytest.raises(SourceChanged, match="no download link"):
        candidate.url_resolver()


def test_robots_disallow_blocks_the_source(fixtures: Path, throttle: http.Throttle) -> None:
    blocked = Site(fixtures, "User-agent: *\nDisallow: /roms/\n")
    with pytest.raises(SourceBlocked, match=r"https://coolrom\.com/roms/genesis/s/"):
        blocked.source(throttle).find("Saint Sword (USA)")
    assert blocked.requests == ["/robots.txt"]


def test_requests_are_spaced_by_the_crawl_delay(
    fixtures: Path, fake_throttle: FakeThrottle
) -> None:
    throttle, sleeps = fake_throttle(1.0)
    site = Site(fixtures, "User-agent: *\nCrawl-delay: 25\n")
    candidate = site.source(throttle).find("Saint Sword (USA)")
    assert candidate is not None
    candidate.url_resolver()
    assert sleeps == [25.0, 25.0]


def test_requests_are_spaced_at_least_ten_seconds(
    fixtures: Path, fake_throttle: FakeThrottle
) -> None:
    throttle, sleeps = fake_throttle(1.0)
    candidate = Site(fixtures, "User-agent: *\n").source(throttle).find("Saint Sword (USA)")
    assert candidate is not None
    candidate.url_resolver()
    assert sleeps == [10.0, 10.0]


@pytest.mark.live
def test_live_section_page() -> None:
    with http.client() as client:
        source = coolrom.CoolromSource("atari7800", client, http.Throttle())
        candidate = source.find("Xenophobe (USA)")
    assert candidate is not None
    assert candidate.filename == "Xenophobe (USA).zip"
