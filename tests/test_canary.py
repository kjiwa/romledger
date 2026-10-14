from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from conftest import FakeThrottle
from romledger import canary, dats, http, igir, registry

VIMM_LIST = "vimm.net/vault/?p=list&system=NES&section=x"
COOLROM_SECTION = "coolrom.com/roms/atari7800/x/"
CONSOLEROMS_LISTING = "www.consoleroms.com/roms/atari-7800"
CONSOLEROMS_DOWNLOAD = "www.consoleroms.com/roms/atari-7800/pole-position-2/download"
CONSOLEROMS_SITEMAP = "www.consoleroms.com/sitemaps/consoles.xml"
EMULAND_INDEX = "www.emu-land.net/en"
ARCHIVE_METADATA = "archive.org/metadata/No-Intro_NES"
IGIR_RELEASE = "api.github.com/repos/emmercm/igir/releases/latest"
Page = httpx.Response | Callable[[], httpx.Response]


def html(text: str) -> httpx.Response:
    return httpx.Response(200, text=text, headers={"Content-Type": "text/html"})


class World:
    def __init__(self, fixtures: Path) -> None:
        coolrom = fixtures / "coolrom"
        section = (coolrom / "section.html").read_text().replace("genesis", "atari7800")
        self.requests: list[tuple[str, str]] = []
        self.pages: dict[str, Page] = {
            "coolrom.com/robots.txt": httpx.Response(200, text="User-agent: *\nCrawl-delay: 10\n"),
            "coolrom.com/roms/": html((coolrom / "index.html").read_text()),
            COOLROM_SECTION: html(section),
            "coolrom.com/dlpop.php?id=6013": html((coolrom / "dlpop.html").read_text()),
            "vimm.net/robots.txt": httpx.Response(200, text=""),
            "vimm.net/vault/": html((fixtures / "vimm" / "vault.html").read_text()),
            VIMM_LIST: html((fixtures / "vimm" / "list.html").read_text()),
            "www.consoleroms.com/robots.txt": httpx.Response(
                200, text="User-agent: *\nDisallow:\n"
            ),
            CONSOLEROMS_SITEMAP: httpx.Response(
                200,
                text=(fixtures / "consoleroms" / "consoles.xml").read_text(),
                headers={"Content-Type": "application/xml"},
            ),
            CONSOLEROMS_LISTING: html((fixtures / "consoleroms" / "listing.html").read_text()),
            CONSOLEROMS_DOWNLOAD: html((fixtures / "consoleroms" / "download.html").read_text()),
            "www.emu-land.net/robots.txt": httpx.Response(
                200, text="User-agent: *\nDisallow: /*act=getmfl\nCrawl-delay: 2\n"
            ),
            EMULAND_INDEX: html((fixtures / "emuland" / "index.html").read_text()),
            "archive.org/robots.txt": httpx.Response(
                200, text="User-agent: *\nDisallow: /control/\n"
            ),
            ARCHIVE_METADATA: httpx.Response(
                200,
                text=(fixtures / "archive" / "metadata.json").read_text(),
                headers={"Content-Type": "application/json"},
            ),
            IGIR_RELEASE: httpx.Response(200, json={"tag_name": f"v{igir.IGIR_VERSION}"}),
        }

    def handle(self, request: httpx.Request) -> httpx.Response:
        key = f"{request.url.host}{request.url.raw_path.decode()}"
        self.requests.append((request.method, key))
        page = self.pages.get(key)
        if page is None:
            return httpx.Response(200 if request.method == "HEAD" else 404)
        return page() if callable(page) else page

    def requested(self) -> list[str]:
        return [key for _, key in self.requests]

    def run(
        self,
        fake_throttle: FakeThrottle,
        token: str | None = None,
    ) -> canary.Report:
        client = httpx.Client(transport=httpx.MockTransport(self.handle), follow_redirects=True)
        throttle, _ = fake_throttle(1.0)
        return canary.run(client, throttle, registry.load(), registry.ignored(), token=token)


@pytest.fixture
def world(fixtures: Path) -> World:
    return World(fixtures)


def keys(report: canary.Report) -> list[str]:
    return [finding.key for finding in report.findings]


def test_all_clear(world: World, fake_throttle: FakeThrottle) -> None:
    report = world.run(fake_throttle)
    assert report == canary.Report([], [], [])
    dat_requests = [key for method, key in world.requests if method == "HEAD"]
    assert len(dat_requests) == len(registry.load())
    assert all(
        urlsplit("https://" + key).hostname == "raw.githubusercontent.com" for key in dat_requests
    )
    assert dats.url("no-intro/Atari - 2600").split("//")[1] in dat_requests


def test_never_requests_the_signed_link_or_a_game_page(
    world: World, fake_throttle: FakeThrottle
) -> None:
    world.run(fake_throttle)
    hosts = {key.split("/", 1)[0] for key in world.requested()}
    assert "dl.coolrom.com" not in hosts
    assert not [
        key for key in world.requested() if key.startswith("vimm.net/vault/") and key[15:].isdigit()
    ]
    assert world.requested().count("coolrom.com/dlpop.php?id=6013") == 1


def test_coolrom_requests_keep_the_crawl_delay(world: World, fake_throttle: FakeThrottle) -> None:
    client = httpx.Client(transport=httpx.MockTransport(world.handle))
    throttle, sleeps = fake_throttle(1.0)
    canary.run(client, throttle, registry.load(), registry.ignored())
    assert sleeps.count(10.0) >= 3


def test_coolrom_missing_registry_code(world: World, fake_throttle: FakeThrottle) -> None:
    index = world.pages["coolrom.com/roms/"]
    assert isinstance(index, httpx.Response)
    world.pages["coolrom.com/roms/"] = html(index.text.replace('href="/roms/psx/"', 'href="/x/"'))
    report = world.run(fake_throttle)
    assert keys(report) == ["coolrom:missing-platform:psx"]
    assert report.findings[0].title.isascii()


def test_coolrom_empty_platform_index_is_page_drift(
    world: World, fake_throttle: FakeThrottle
) -> None:
    world.pages["coolrom.com/roms/"] = html("<html>moved</html>")
    report = world.run(fake_throttle)
    assert keys(report) == ["coolrom:contract:platform-links"]
    assert report.inconclusive == []


def test_coolrom_new_platform_proposes_a_registry_line(
    world: World, fake_throttle: FakeThrottle
) -> None:
    index = world.pages["coolrom.com/roms/"]
    assert isinstance(index, httpx.Response)
    world.pages["coolrom.com/roms/"] = html(
        index.text.replace("</body>", '<a href="/roms/zx81/">ZX81</a></body>')
    )
    report = world.run(fake_throttle)
    assert keys(report) == ["coolrom:new-platform:zx81"]
    assert 'coolrom = "zx81"' in report.findings[0].detail


def test_coolrom_ignored_codes_are_in_the_index(world: World) -> None:
    index = world.pages["coolrom.com/roms/"]
    assert isinstance(index, httpx.Response)
    for code in registry.ignored()["coolrom"]:
        assert f'href="/roms/{code}/"' in index.text


@pytest.mark.parametrize(
    "page",
    [
        html("<html><body>moved</body></html>"),
        httpx.Response(404),
        html('<div class="header"><a href="/roms/atari7800/">Atari 7800</a></div>'),
    ],
    ids=["no-rows-no-breadcrumb", "not-found", "no-rows"],
)
def test_coolrom_section_contract(
    world: World, fake_throttle: FakeThrottle, page: httpx.Response
) -> None:
    world.pages[COOLROM_SECTION] = page
    report = world.run(fake_throttle)
    assert keys(report) == ["coolrom:contract:section"]
    assert "/roms/atari7800/x/" in report.findings[0].detail
    assert not [key for key in world.requested() if "dlpop" in key]


def test_coolrom_download_contract(world: World, fake_throttle: FakeThrottle) -> None:
    world.pages["coolrom.com/dlpop.php?id=6013"] = html("<html>no script</html>")
    report = world.run(fake_throttle)
    assert keys(report) == ["coolrom:contract:download-link"]
    assert "no download link" in report.findings[0].detail


def test_consoleroms_requests_never_touch_the_download_host(
    world: World, fake_throttle: FakeThrottle
) -> None:
    world.run(fake_throttle)
    hosts = {key.split("/", 1)[0] for key in world.requested()}
    assert "downloads.consoleroms.com" not in hosts
    assert world.requested().count(CONSOLEROMS_DOWNLOAD) == 1


def test_consoleroms_missing_registry_code(world: World, fake_throttle: FakeThrottle) -> None:
    sitemap = world.pages[CONSOLEROMS_SITEMAP]
    assert isinstance(sitemap, httpx.Response)
    world.pages[CONSOLEROMS_SITEMAP] = httpx.Response(
        200, text=sitemap.text.replace("/roms/snes<", "/other/snes<")
    )
    report = world.run(fake_throttle)
    assert keys(report) == ["consoleroms:missing-platform:snes"]


def test_consoleroms_empty_platform_list_is_page_drift(
    world: World, fake_throttle: FakeThrottle
) -> None:
    world.pages[CONSOLEROMS_SITEMAP] = httpx.Response(200, text="<urlset></urlset>")
    report = world.run(fake_throttle)
    assert keys(report) == ["consoleroms:contract:platform-links"]
    assert report.inconclusive == []


def test_consoleroms_new_platform_proposes_a_registry_line(
    world: World, fake_throttle: FakeThrottle
) -> None:
    sitemap = world.pages[CONSOLEROMS_SITEMAP]
    assert isinstance(sitemap, httpx.Response)
    world.pages[CONSOLEROMS_SITEMAP] = httpx.Response(
        200,
        text=sitemap.text.replace(
            "</urlset>", "<url><loc>https://www.consoleroms.com/roms/vic-20</loc></url></urlset>"
        ),
    )
    report = world.run(fake_throttle)
    assert keys(report) == ["consoleroms:new-platform:vic-20"]
    assert 'consoleroms = "vic-20"' in report.findings[0].detail


def test_consoleroms_ignored_codes_are_in_the_sitemap(world: World) -> None:
    sitemap = world.pages[CONSOLEROMS_SITEMAP]
    assert isinstance(sitemap, httpx.Response)
    for code in registry.ignored()["consoleroms"]:
        assert f"/roms/{code}<" in sitemap.text


@pytest.mark.parametrize(
    "page",
    [
        html("<html><body>moved</body></html>"),
        httpx.Response(404),
    ],
    ids=["no-rows", "not-found"],
)
def test_consoleroms_listing_contract(
    world: World, fake_throttle: FakeThrottle, page: httpx.Response
) -> None:
    world.pages[CONSOLEROMS_LISTING] = page
    report = world.run(fake_throttle)
    assert keys(report) == ["consoleroms:contract:listing"]
    assert "/roms/atari-7800" in report.findings[0].detail
    assert CONSOLEROMS_DOWNLOAD not in world.requested()


@pytest.mark.parametrize(
    "page",
    [
        html("<html>no link</html>"),
        html('<a href="https://downloads.consoleroms.com/roms/x.exe">click here</a>'),
    ],
    ids=["no-link", "wrong-suffix"],
)
def test_consoleroms_download_contract(
    world: World, fake_throttle: FakeThrottle, page: httpx.Response
) -> None:
    world.pages[CONSOLEROMS_DOWNLOAD] = page
    report = world.run(fake_throttle)
    assert keys(report) == ["consoleroms:contract:download-link"]


def test_emuland_requests_keep_the_crawl_delay(world: World, fake_throttle: FakeThrottle) -> None:
    client = httpx.Client(transport=httpx.MockTransport(world.handle))
    throttle, sleeps = fake_throttle(1.0)
    canary.run(client, throttle, registry.load(), registry.ignored())
    assert 2.0 in sleeps


def test_emuland_missing_registry_code(world: World, fake_throttle: FakeThrottle) -> None:
    index = world.pages[EMULAND_INDEX]
    assert isinstance(index, httpx.Response)
    world.pages[EMULAND_INDEX] = html(index.text.replace("/en/consoles/snes", "/en/x"))
    report = world.run(fake_throttle)
    assert keys(report) == ["emuland:missing-platform:consoles/snes"]


def test_emuland_empty_platform_index_is_page_drift(
    world: World, fake_throttle: FakeThrottle
) -> None:
    world.pages[EMULAND_INDEX] = html("<html>moved</html>")
    report = world.run(fake_throttle)
    assert keys(report) == ["emuland:contract:platform-links"]
    assert report.inconclusive == []


def test_emuland_new_platform_proposes_a_registry_line(
    world: World, fake_throttle: FakeThrottle
) -> None:
    index = world.pages[EMULAND_INDEX]
    assert isinstance(index, httpx.Response)
    world.pages[EMULAND_INDEX] = html(
        index.text.replace("</body>", '<a href="/en/consoles/odyssey2">x</a></body>')
    )
    report = world.run(fake_throttle)
    assert keys(report) == ["emuland:new-platform:consoles/odyssey2"]
    assert 'emuland = "consoles/odyssey2"' in report.findings[0].detail


def test_emuland_links_outside_the_platform_groups_are_not_platforms(
    world: World, fake_throttle: FakeThrottle
) -> None:
    index = world.pages[EMULAND_INDEX]
    assert isinstance(index, httpx.Response)
    world.pages[EMULAND_INDEX] = html(
        index.text.replace("</body>", '<a href="/en/news/today">x</a></body>')
    )
    assert world.run(fake_throttle) == canary.Report([], [], [])


def test_emuland_ignored_codes_are_in_the_index(world: World) -> None:
    index = world.pages[EMULAND_INDEX]
    assert isinstance(index, httpx.Response)
    for code in registry.ignored()["emuland"]:
        assert f'href="/en/{code}"' in index.text


def test_vimm_missing_registry_code(world: World, fake_throttle: FakeThrottle) -> None:
    page = world.pages["vimm.net/vault/"]
    assert isinstance(page, httpx.Response)
    world.pages["vimm.net/vault/"] = html(page.text.replace('href="/vault/PS3"', 'href="/x"'))
    report = world.run(fake_throttle)
    assert keys(report) == ["vimm:missing-platform:PS3"]
    assert "PS3" in report.findings[0].detail


def test_missing_and_new_keys_never_collide(world: World, fake_throttle: FakeThrottle) -> None:
    page = world.pages["vimm.net/vault/"]
    assert isinstance(page, httpx.Response)
    text = page.text.replace('href="/vault/PS3"', 'href="/vault/PS4"')
    text = text.replace('href="/vault/PS2"', 'href="/vault/PS5"')
    world.pages["vimm.net/vault/"] = html(text)
    found = keys(world.run(fake_throttle))
    assert found == [
        "vimm:missing-platform:PS2",
        "vimm:missing-platform:PS3",
        "vimm:new-platform:PS4",
        "vimm:new-platform:PS5",
    ]


def test_vimm_new_platform_ignores_numeric_links_and_ignored_codes(
    world: World, fake_throttle: FakeThrottle
) -> None:
    page = world.pages["vimm.net/vault/"]
    assert isinstance(page, httpx.Response)
    assert 'href="/vault/WiiWare"' in page.text
    assert 'href="/vault/123"' in page.text
    world.pages["vimm.net/vault/"] = html(
        page.text.replace("</body>", '<a href="/vault/Amiga">Amiga</a></body>')
    )
    report = world.run(fake_throttle)
    assert keys(report) == ["vimm:new-platform:Amiga"]
    assert 'vimm = "Amiga"' in report.findings[0].detail


def test_vimm_list_contract(world: World, fake_throttle: FakeThrottle) -> None:
    world.pages[VIMM_LIST] = html('<a href="/vault/NES">NES</a>')
    report = world.run(fake_throttle)
    assert keys(report) == ["vimm:contract:list"]


@pytest.mark.parametrize(
    "body",
    [
        "<html>not json</html>",
        "[]",
        '{"files": []}',
        '{"files": [{"name": "a.zip"}]}',
    ],
)
def test_archive_contract(world: World, fake_throttle: FakeThrottle, body: str) -> None:
    world.pages[ARCHIVE_METADATA] = httpx.Response(200, text=body)
    assert keys(world.run(fake_throttle)) == ["internet-archive:contract:metadata"]


def test_dat_missing(world: World, fake_throttle: FakeThrottle) -> None:
    key = dats.url(registry.load()["nes"].dat).split("//")[1]
    world.pages[key] = httpx.Response(404)
    report = world.run(fake_throttle)
    assert keys(report) == ["dat:missing:nes"]
    assert "HTTP 404" in report.findings[0].detail


def test_igir_newer_release(world: World, fake_throttle: FakeThrottle) -> None:
    world.pages[IGIR_RELEASE] = httpx.Response(200, json={"tag_name": "v99.0.0"})
    report = world.run(fake_throttle)
    assert keys(report) == ["igir:update:v99.0.0"]
    assert "IGIR_VERSION" in report.findings[0].detail


def test_igir_same_release_without_prefix(world: World, fake_throttle: FakeThrottle) -> None:
    world.pages[IGIR_RELEASE] = httpx.Response(200, json={"tag_name": igir.IGIR_VERSION})
    assert world.run(fake_throttle).findings == []


@pytest.mark.parametrize("body", [{"tag": "v1"}, {"tag_name": 5}, {"tag_name": ""}, [1]])
def test_igir_contract(world: World, fake_throttle: FakeThrottle, body: object) -> None:
    world.pages[IGIR_RELEASE] = httpx.Response(200, json=body)
    assert keys(world.run(fake_throttle)) == ["igir:contract:release"]


def test_igir_not_json_is_a_contract_finding(world: World, fake_throttle: FakeThrottle) -> None:
    world.pages[IGIR_RELEASE] = httpx.Response(200, text="<html>")
    assert keys(world.run(fake_throttle)) == ["igir:contract:release"]


def test_igir_token_is_sent_only_when_set(world: World, fake_throttle: FakeThrottle) -> None:
    seen: list[str | None] = []

    def release() -> httpx.Response:
        return httpx.Response(200, json={"tag_name": igir.IGIR_VERSION})

    original = world.handle

    def spy(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            seen.append(request.headers.get("Authorization"))
        return original(request)

    world.pages[IGIR_RELEASE] = release
    client = httpx.Client(transport=httpx.MockTransport(spy))
    throttle, _ = fake_throttle(1.0)
    for token in (None, "t0ken"):
        canary.run(client, throttle, registry.load(), registry.ignored(), token=token)
    assert seen == [None, "Bearer t0ken"]


def timeout() -> httpx.Response:
    raise httpx.ReadTimeout("")


CHALLENGE = html("<html><title>Just a moment...</title></html>")
SITES = {
    "coolrom": "coolrom.com/roms/",
    "vimm": "vimm.net/vault/",
    "consoleroms": CONSOLEROMS_SITEMAP,
    "emuland": EMULAND_INDEX,
    "archive": ARCHIVE_METADATA,
}


GROUPS = {
    "coolrom": "coolrom",
    "vimm": "vimm",
    "consoleroms": "consoleroms",
    "emuland": "emuland",
    "archive": "internet-archive",
}


@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize(
    "page",
    [httpx.Response(403), httpx.Response(429), httpx.Response(503), timeout, CHALLENGE],
    ids=["403", "429", "503", "timeout", "challenge"],
)
def test_inconclusive_site_is_a_note_not_a_finding(
    world: World, fake_throttle: FakeThrottle, site: str, page: Page
) -> None:
    first = SITES[site]
    world.pages[first] = page
    report = world.run(fake_throttle)
    assert report.findings == []
    assert len(report.notes) == 1
    assert first in report.notes[0]
    assert report.notes[0].isascii()
    assert report.inconclusive[0] == GROUPS[site]
    assert any(urlsplit("https://" + key).hostname == "api.github.com" for key in world.requested())


def test_inconclusive_site_skips_its_remaining_checks(
    world: World, fake_throttle: FakeThrottle
) -> None:
    world.pages["coolrom.com/roms/"] = httpx.Response(403)
    world.run(fake_throttle)
    assert COOLROM_SECTION not in world.requested()
    assert VIMM_LIST in world.requested()


def test_findings_before_an_inconclusive_response_are_kept(
    world: World, fake_throttle: FakeThrottle
) -> None:
    world.pages[COOLROM_SECTION] = html("<html></html>")
    world.pages["coolrom.com/dlpop.php?id=6013"] = httpx.Response(200)
    world.pages["vimm.net/vault/"] = httpx.Response(429)
    report = world.run(fake_throttle)
    assert keys(report) == ["coolrom:contract:section"]
    assert len(report.notes) == 1


def test_robots_refusal_is_a_note(world: World, fake_throttle: FakeThrottle) -> None:
    world.pages["vimm.net/robots.txt"] = httpx.Response(200, text="User-agent: *\nDisallow: /\n")
    report = world.run(fake_throttle)
    assert report.findings == []
    assert "robots.txt" in report.notes[0]


def test_dat_server_error_stops_the_dat_checks(world: World, fake_throttle: FakeThrottle) -> None:
    first = dats.url(next(iter(registry.load().values())).dat).split("//")[1]
    world.pages[first] = httpx.Response(503)
    report = world.run(fake_throttle)
    assert report.findings == []
    assert report.notes == [f"https://{first}: HTTP 503"]
    assert len([method for method, _ in world.requests if method == "HEAD"]) == 1


def test_igir_rate_limit_is_a_note(world: World, fake_throttle: FakeThrottle) -> None:
    world.pages[IGIR_RELEASE] = httpx.Response(403)
    report = world.run(fake_throttle)
    assert report.findings == []
    assert report.notes == [f"https://{IGIR_RELEASE}: HTTP 403"]


def test_network_error_on_igir_is_a_note(world: World, fake_throttle: FakeThrottle) -> None:
    world.pages[IGIR_RELEASE] = timeout
    report = world.run(fake_throttle)
    assert report.findings == []
    assert report.notes == [f"https://{IGIR_RELEASE}: request failed (ReadTimeout)"]


def test_cloudflare_mitigation_header_is_a_challenge(
    world: World, fake_throttle: FakeThrottle
) -> None:
    world.pages["vimm.net/vault/"] = httpx.Response(200, headers={"cf-mitigated": "challenge"})
    report = world.run(fake_throttle)
    assert report.findings == []
    assert report.notes == ["https://vimm.net/vault/: bot challenge page"]


def test_a_game_title_in_json_is_not_a_challenge(world: World, fake_throttle: FakeThrottle) -> None:
    body = '{"files": [{"name": "Just a Moment.zip", "md5": "0"}]}'
    world.pages[ARCHIVE_METADATA] = httpx.Response(
        200, text=body, headers={"Content-Type": "application/json"}
    )
    assert world.run(fake_throttle) == canary.Report([], [], [])


@pytest.mark.live
def test_live_canary() -> None:
    with http.client() as client:
        report = canary.run(client, http.Throttle(), registry.load(), registry.ignored())
    assert report.findings == []


def test_the_cloudflare_beacon_on_a_normal_page_is_not_a_challenge(
    world: World, fake_throttle: FakeThrottle
) -> None:
    page = world.pages["coolrom.com/roms/"]
    assert isinstance(page, httpx.Response)
    beacon = '<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'
    world.pages["coolrom.com/roms/"] = html(page.text.replace("</body>", f"{beacon}</body>"))
    assert world.run(fake_throttle) == canary.Report([], [], [])


def test_inconclusive_lists_the_group_and_every_skipped_check(
    world: World, fake_throttle: FakeThrottle
) -> None:
    world.pages["coolrom.com/roms/"] = httpx.Response(403)
    assert world.run(fake_throttle).inconclusive == [
        "coolrom",
        "coolrom:contract:platform-links",
        "coolrom:missing-platform",
        "coolrom:new-platform",
        "coolrom:contract:section",
        "coolrom:contract:download-link",
    ]


def test_inconclusive_section_skips_the_download_check(
    world: World, fake_throttle: FakeThrottle
) -> None:
    world.pages[COOLROM_SECTION] = httpx.Response(503)
    assert world.run(fake_throttle).inconclusive == [
        "coolrom",
        "coolrom:contract:section",
        "coolrom:contract:download-link",
    ]


def test_section_drift_leaves_the_download_check_unverified(
    world: World, fake_throttle: FakeThrottle
) -> None:
    world.pages[COOLROM_SECTION] = html("<html></html>")
    report = world.run(fake_throttle)
    assert keys(report) == ["coolrom:contract:section"]
    assert report.notes == []
    assert report.inconclusive == ["coolrom:contract:download-link"]


def test_unverified_dat_prefixes_cover_the_skipped_dats(
    world: World, fake_throttle: FakeThrottle
) -> None:
    slugs = list(registry.load())
    first = dats.url(registry.load()[slugs[1]].dat).split("//")[1]
    world.pages[first] = httpx.Response(503)
    report = world.run(fake_throttle)
    assert report.inconclusive == ["dat", *(f"dat:missing:{slug}" for slug in slugs[1:])]


@pytest.mark.parametrize("status", [301, 400, 403, 500])
def test_dat_statuses_other_than_404_are_notes(
    world: World, fake_throttle: FakeThrottle, status: int
) -> None:
    first = dats.url(next(iter(registry.load().values())).dat).split("//")[1]
    world.pages[first] = httpx.Response(status)
    report = world.run(fake_throttle)
    assert report.findings == []
    assert report.notes == [f"https://{first}: HTTP {status}"]
    assert report.inconclusive[0] == "dat"


def test_igir_request_does_not_follow_redirects_and_keeps_the_token_local(
    world: World, fake_throttle: FakeThrottle
) -> None:
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.headers.get("Authorization")))
        if request.url.host == "api.github.com":
            return httpx.Response(302, headers={"Location": "https://evil.example/x"})
        return world.handle(request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    throttle, _ = fake_throttle(1.0)
    secret = "t0ken"  # noqa: S105
    report = canary.run(client, throttle, registry.load(), registry.ignored(), token=secret)
    assert report.findings == []
    assert report.notes == [f"{canary.IGIR_RELEASE_URL}: HTTP 302"]
    assert report.inconclusive == ["igir", "igir:contract:release", "igir:update"]
    assert [auth for host, auth in seen if auth] == ["Bearer t0ken"]
    assert all(host != "evil.example" for host, _ in seen)
    assert "Authorization" not in client.headers
