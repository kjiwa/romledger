import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial

import httpx

from romledger import dats, http, igir, registry
from romledger.sources import SOURCES, consoleroms
from romledger.sources.base import Site
from romledger.sources.errors import FetchError, SourceBlocked, SourceChanged

VIMM_URL = "https://vimm.net"
VIMM_SYSTEM = "NES"
CONSOLEROMS_PLATFORM = "atari-7800"
IGIR_RELEASE_URL = "https://api.github.com/repos/emmercm/igir/releases/latest"
VIMM_PLATFORM_LINK = re.compile(r'href="/vault/([A-Za-z0-9-]+)"')
VIMM_ROW_LINK = re.compile(r'href="/vault/\d+"')
CONSOLEROMS_PLATFORM_LINK = re.compile(
    r"<loc>https://www\.consoleroms\.com/roms/([a-z0-9-]+)</loc>"
)
CHALLENGE_MARKERS = ("just a moment", "checking if you are human")


@dataclass(frozen=True)
class Finding:
    key: str
    title: str
    detail: str


@dataclass(frozen=True)
class Report:
    findings: list[Finding]
    notes: list[str]
    inconclusive: list[str]


class Inconclusive(Exception):
    pass


class Skipped(Exception):
    pass


class Drift(Exception):
    pass


Check = Callable[[], list[Finding]]


@dataclass(frozen=True)
class Step:
    check: Check
    keys: tuple[str, ...]


def run(
    client: httpx.Client,
    throttle: http.Throttle,
    entries: Mapping[str, registry.Entry],
    ignored: Mapping[str, frozenset[str]],
    pinned_igir: str = igir.IGIR_VERSION,
    token: str | None = None,
) -> Report:
    return _merge(
        [
            _run_steps("vimm", _vimm_steps(client, throttle, entries, ignored["vimm"])),
            _run_steps(
                "consoleroms",
                _consoleroms_steps(client, throttle, entries, ignored["consoleroms"]),
            ),
            _run_steps("dat", _dat_steps(client, throttle, entries)),
            _run_steps("igir", _igir_steps(client, throttle, pinned_igir, token)),
        ]
    )


def _merge(reports: Sequence[Report]) -> Report:
    return Report(
        [finding for report in reports for finding in report.findings],
        [note for report in reports for note in report.notes],
        [prefix for report in reports for prefix in report.inconclusive],
    )


def _run_steps(group: str, steps: Sequence[Step]) -> Report:
    report = Report([], [], [])
    for index, step in enumerate(steps):
        try:
            report.findings.extend(step.check())
        except Skipped:
            report.inconclusive.extend(step.keys)
        except Inconclusive as note:
            report.notes.append(str(note))
            report.inconclusive.append(group)
            report.inconclusive.extend(key for later in steps[index:] for key in later.keys)
            break
    return report


def _step(keys: tuple[str, ...], title: str, check: Check) -> Step:
    def guarded() -> list[Finding]:
        try:
            return check()
        except Drift as error:
            detail = str(error)
        except SourceChanged as error:
            detail = f"{error.url}: {error.what}"
        return [Finding(keys[0], title, detail)]

    return Step(guarded, keys)


def _vimm_steps(
    client: httpx.Client,
    throttle: http.Throttle,
    entries: Mapping[str, registry.Entry],
    ignored: frozenset[str],
) -> list[Step]:
    site = Site(VIMM_URL, SOURCES["vimm"].hosts, http.DEFAULT_GAP, client, throttle)
    return [
        _step(
            ("vimm:contract:platform-links", "vimm:missing-platform", "vimm:new-platform"),
            "Vimm's Lair platform list changed",
            partial(_vimm_platforms, site, entries, ignored),
        ),
        _step(
            ("vimm:contract:list",),
            "Vimm's Lair list page changed",
            partial(_vimm_list, site),
        ),
    ]


def _vimm_platforms(
    site: Site, entries: Mapping[str, registry.Entry], ignored: frozenset[str]
) -> list[Finding]:
    url = f"{VIMM_URL}/vault/"
    codes = VIMM_PLATFORM_LINK.findall(_page(site, url).text)
    found = {code for code in codes if not code.isdigit()}
    mapped = {entry.vimm for entry in entries.values() if entry.vimm}
    return _platform_findings("vimm", url, found, mapped, ignored)


def _vimm_list(site: Site) -> list[Finding]:
    url = f"{VIMM_URL}/vault/?p=list&system={VIMM_SYSTEM}&section=x"
    if not VIMM_ROW_LINK.search(_page(site, url).text):
        raise Drift(f"{url}: no game row links found")
    return []


def _consoleroms_steps(
    client: httpx.Client,
    throttle: http.Throttle,
    entries: Mapping[str, registry.Entry],
    ignored: frozenset[str],
) -> list[Step]:
    site = Site(consoleroms.BASE_URL, consoleroms.HOSTS, consoleroms.MIN_GAP, client, throttle)
    first_rows: list[consoleroms.Row] = []
    return [
        _step(
            (
                "consoleroms:contract:platform-links",
                "consoleroms:missing-platform",
                "consoleroms:new-platform",
            ),
            "ConsoleRoms platform list changed",
            partial(_consoleroms_platforms, site, entries, ignored),
        ),
        _step(
            ("consoleroms:contract:listing",),
            "ConsoleRoms listing page changed",
            partial(_consoleroms_listing, site, first_rows),
        ),
        _step(
            ("consoleroms:contract:download-link",),
            "ConsoleRoms download page changed",
            partial(_consoleroms_download, site, first_rows),
        ),
    ]


def _consoleroms_platforms(
    site: Site, entries: Mapping[str, registry.Entry], ignored: frozenset[str]
) -> list[Finding]:
    url = f"{consoleroms.BASE_URL}/sitemaps/consoles.xml"
    found = set(CONSOLEROMS_PLATFORM_LINK.findall(_page(site, url).text))
    mapped = {entry.consoleroms for entry in entries.values() if entry.consoleroms}
    return _platform_findings("consoleroms", url, found, mapped, ignored)


def _consoleroms_listing(site: Site, first_rows: list[consoleroms.Row]) -> list[Finding]:
    url = f"{consoleroms.BASE_URL}/roms/{CONSOLEROMS_PLATFORM}"
    rows, _ = consoleroms.parse_listing(_page(site, url).text, CONSOLEROMS_PLATFORM, url)
    first_rows.append(rows[0])
    return []


def _consoleroms_download(site: Site, first_rows: list[consoleroms.Row]) -> list[Finding]:
    if not first_rows:
        raise Skipped
    url = f"{consoleroms.BASE_URL}/roms/{CONSOLEROMS_PLATFORM}/{first_rows[0].slug}/download"
    consoleroms.parse_download_link(_page(site, url).text, url)
    return []


def _platform_findings(
    site: str, url: str, found: set[str], mapped: set[str], ignored: frozenset[str]
) -> list[Finding]:
    if not found:
        raise Drift(f"{url}: no platform links found")
    findings = [
        Finding(
            f"{site}:missing-platform:{code}",
            f"{site} no longer lists a registry platform: {code}",
            f"{url} has no link for {code}. Correct the {site} code in "
            "src/romledger/platforms.toml.",
        )
        for code in sorted(mapped - found)
    ]
    findings.extend(
        Finding(
            f"{site}:new-platform:{code}",
            f"{site} lists a platform missing from the registry: {code}",
            f'{url} links {code}. Add `{site} = "{code}"` to its platform in '
            f"src/romledger/platforms.toml, or add it to [ignore] {site}.",
        )
        for code in sorted(found - mapped - ignored)
    )
    return findings


def _dat_steps(
    client: httpx.Client, throttle: http.Throttle, entries: Mapping[str, registry.Entry]
) -> list[Step]:
    return [
        Step(partial(_dat_exists, client, throttle, entry), (f"dat:missing:{entry.slug}",))
        for entry in entries.values()
    ]


def _dat_exists(
    client: httpx.Client, throttle: http.Throttle, entry: registry.Entry
) -> list[Finding]:
    url = dats.url(entry.dat)
    status = _send(client, throttle, "HEAD", url).status_code
    if status == httpx.codes.OK:
        return []
    if status != httpx.codes.NOT_FOUND:
        raise Inconclusive(f"{url}: HTTP {status}")
    return [
        Finding(
            f"dat:missing:{entry.slug}",
            f"libretro-database has no DAT for {entry.slug}",
            f"{url}: HTTP 404. Correct dat for {entry.slug} in src/romledger/platforms.toml.",
        )
    ]


def _igir_steps(
    client: httpx.Client, throttle: http.Throttle, pinned: str, token: str | None
) -> list[Step]:
    return [
        _step(
            ("igir:contract:release", "igir:update"),
            "igir release lookup changed",
            partial(_igir_update, client, throttle, pinned, token),
        )
    ]


def _igir_update(
    client: httpx.Client, throttle: http.Throttle, pinned: str, token: str | None
) -> list[Finding]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = _send(client, throttle, "GET", IGIR_RELEASE_URL, headers, follow_redirects=False)
    if response.status_code != httpx.codes.OK:
        raise Inconclusive(f"{IGIR_RELEASE_URL}: HTTP {response.status_code}")
    tag = _release_tag(response)
    if tag.removeprefix("v") == pinned:
        return []
    return [
        Finding(
            f"igir:update:{tag}",
            f"igir {tag} is out; romledger pins {pinned}",
            f"Run `uv run pytest -m igir --no-cov`, then set IGIR_VERSION to "
            f"{tag.removeprefix('v')} in src/romledger/igir.py.",
        )
    ]


def _release_tag(response: httpx.Response) -> str:
    try:
        tag = response.json()["tag_name"]
    except (ValueError, KeyError, TypeError) as error:
        raise Drift(f"{IGIR_RELEASE_URL}: response has no tag_name") from error
    if not isinstance(tag, str) or not tag:
        raise Drift(f"{IGIR_RELEASE_URL}: tag_name is not a string")
    return tag


def _page(site: Site, url: str) -> httpx.Response:
    try:
        response = site.get(url, expect=(httpx.codes.OK, httpx.codes.NOT_FOUND))
    except (FetchError, SourceBlocked) as error:
        raise Inconclusive(str(error)) from error
    except httpx.HTTPError as error:
        raise Inconclusive(_unreachable(url, error)) from error
    if response.status_code == httpx.codes.NOT_FOUND:
        raise Drift(f"{url}: HTTP 404")
    if _is_challenge(response):
        raise Inconclusive(f"{url}: bot challenge page")
    return response


def _send(
    client: httpx.Client,
    throttle: http.Throttle,
    method: str,
    url: str,
    headers: Mapping[str, str] | None = None,
    *,
    follow_redirects: bool = True,
) -> httpx.Response:
    throttle.wait(url)
    try:
        return client.request(method, url, headers=headers, follow_redirects=follow_redirects)
    except httpx.HTTPError as error:
        raise Inconclusive(_unreachable(url, error)) from error


def _unreachable(url: str, error: httpx.HTTPError) -> str:
    return f"{url}: request failed ({str(error) or type(error).__name__})"


def _is_challenge(response: httpx.Response) -> bool:
    if response.headers.get("cf-mitigated") == "challenge":
        return True
    if "text/html" not in response.headers.get("content-type", ""):
        return False
    text = response.text.lower()
    return any(marker in text for marker in CHALLENGE_MARKERS)
