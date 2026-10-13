import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial

import httpx

from romledger import dats, http, igir, registry
from romledger.sources import coolrom, internet_archive
from romledger.sources.base import Site
from romledger.sources.errors import FetchError, SourceBlocked, SourceChanged

COOLROM_PLATFORM = "atari7800"
VIMM_URL = "https://vimm.net"
VIMM_HOSTS = ("vimm.net",)
VIMM_SYSTEM = "NES"
ARCHIVE_ITEM = "No-Intro_NES"
IGIR_RELEASE_URL = "https://api.github.com/repos/emmercm/igir/releases/latest"
COOLROM_PLATFORM_LINK = re.compile(r'href="/roms/([a-z0-9]+)/"')
VIMM_PLATFORM_LINK = re.compile(r'href="/vault/([A-Za-z0-9-]+)"')
VIMM_ROW_LINK = re.compile(r'href="/vault/\d+"')
CHALLENGE_MARKERS = ("just a moment", "checking if you are human")
TRANSIENT_STATUSES = (httpx.codes.FORBIDDEN, httpx.codes.TOO_MANY_REQUESTS)


@dataclass(frozen=True)
class Finding:
    key: str
    title: str
    detail: str


@dataclass(frozen=True)
class Report:
    findings: list[Finding]
    notes: list[str]


class Inconclusive(Exception):
    pass


class Drift(Exception):
    pass


Check = Callable[[], list[Finding]]


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
            _run_checks(_coolrom_checks(client, throttle, entries, ignored["coolrom"])),
            _run_checks(_vimm_checks(client, throttle, entries, ignored["vimm"])),
            _run_checks(_archive_checks(client, throttle)),
            _run_checks(_dat_checks(client, throttle, entries)),
            _run_checks(_igir_checks(client, throttle, pinned_igir, token)),
        ]
    )


def _merge(reports: Sequence[Report]) -> Report:
    return Report(
        [finding for report in reports for finding in report.findings],
        [note for report in reports for note in report.notes],
    )


def _run_checks(checks: Sequence[Check]) -> Report:
    findings: list[Finding] = []
    for check in checks:
        try:
            findings.extend(check())
        except Inconclusive as note:
            return Report(findings, [str(note)])
    return Report(findings, [])


def _guarded(key: str, title: str, check: Check) -> Check:
    def guarded() -> list[Finding]:
        try:
            return check()
        except Drift as error:
            detail = str(error)
        except SourceChanged as error:
            detail = f"{error.url}: {error.what}"
        return [Finding(key, title, detail)]

    return guarded


def _coolrom_checks(
    client: httpx.Client,
    throttle: http.Throttle,
    entries: Mapping[str, registry.Entry],
    ignored: frozenset[str],
) -> list[Check]:
    site = Site(coolrom.BASE_URL, coolrom.HOSTS, coolrom.MIN_GAP, client, throttle)
    first_rows: list[coolrom.Row] = []
    return [
        _guarded(
            "coolrom:contract:platform-links",
            "CoolROM platform list changed",
            partial(_coolrom_platforms, site, entries, ignored),
        ),
        _guarded(
            "coolrom:contract:section",
            "CoolROM section page changed",
            partial(_coolrom_section, site, first_rows),
        ),
        _guarded(
            "coolrom:contract:download-link",
            "CoolROM download page changed",
            partial(_coolrom_download, site, first_rows),
        ),
    ]


def _coolrom_platforms(
    site: Site, entries: Mapping[str, registry.Entry], ignored: frozenset[str]
) -> list[Finding]:
    url = f"{coolrom.BASE_URL}/roms/"
    found = set(COOLROM_PLATFORM_LINK.findall(_page(site, url).text))
    mapped = {entry.coolrom for entry in entries.values() if entry.coolrom}
    return _platform_findings("coolrom", url, found, mapped, ignored)


def _coolrom_section(site: Site, first_rows: list[coolrom.Row]) -> list[Finding]:
    url = f"{coolrom.BASE_URL}/roms/{COOLROM_PLATFORM}/x/"
    rows = coolrom.parse_section(_page(site, url).text, COOLROM_PLATFORM, url)
    if not rows:
        raise Drift(f"{url}: no game rows found")
    first_rows.append(rows[0])
    return []


def _coolrom_download(site: Site, first_rows: list[coolrom.Row]) -> list[Finding]:
    if first_rows:
        url = f"{coolrom.BASE_URL}/dlpop.php?id={first_rows[0].id}"
        coolrom.parse_signed_link(_page(site, url).text, url)
    return []


def _vimm_checks(
    client: httpx.Client,
    throttle: http.Throttle,
    entries: Mapping[str, registry.Entry],
    ignored: frozenset[str],
) -> list[Check]:
    site = Site(VIMM_URL, VIMM_HOSTS, http.DEFAULT_GAP, client, throttle)
    return [
        _guarded(
            "vimm:contract:platform-links",
            "Vimm's Lair platform list changed",
            partial(_vimm_platforms, site, entries, ignored),
        ),
        _guarded(
            "vimm:contract:list",
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


def _platform_findings(
    site: str, url: str, found: set[str], mapped: set[str], ignored: frozenset[str]
) -> list[Finding]:
    findings = []
    missing = sorted(mapped - found)
    if missing:
        findings.append(
            Finding(
                f"{site}:contract:platform-links",
                f"{site} no longer lists platforms: {', '.join(missing)}",
                f"{url} has no link for registry codes {', '.join(missing)}. "
                f"Correct the {site} codes in src/romledger/platforms.toml.",
            )
        )
    for code in sorted(found - mapped - ignored):
        findings.append(
            Finding(
                f"{site}:new-platform:{code}",
                f"{site} lists a platform missing from the registry: {code}",
                f'{url} links {code}. Add `{site} = "{code}"` to its platform in '
                f"src/romledger/platforms.toml, or add it to [ignore] {site}.",
            )
        )
    return findings


def _archive_checks(client: httpx.Client, throttle: http.Throttle) -> list[Check]:
    site = Site(
        internet_archive.BASE_URL, internet_archive.HOSTS, http.DEFAULT_GAP, client, throttle
    )
    return [
        _guarded(
            "internet-archive:contract:metadata",
            "Internet Archive metadata changed",
            partial(_archive_metadata, site),
        )
    ]


def _archive_metadata(site: Site) -> list[Finding]:
    url = f"{internet_archive.BASE_URL}/metadata/{ARCHIVE_ITEM}"
    files = internet_archive.index(_page(site, url), url, ARCHIVE_ITEM)
    if not any(isinstance(entry.get("md5"), str) for entry in files.values()):
        raise Drift(f"{url}: no file entry has an md5")
    return []


def _dat_checks(
    client: httpx.Client, throttle: http.Throttle, entries: Mapping[str, registry.Entry]
) -> list[Check]:
    return [partial(_dat_exists, client, throttle, entry) for entry in entries.values()]


def _dat_exists(
    client: httpx.Client, throttle: http.Throttle, entry: registry.Entry
) -> list[Finding]:
    url = dats.url(entry.dat)
    status = _send(client, throttle, "HEAD", url).status_code
    if status == httpx.codes.OK:
        return []
    return [
        Finding(
            f"dat:missing:{entry.slug}",
            f"libretro-database has no DAT for {entry.slug}",
            f"{url}: HTTP {status}. Correct dat for {entry.slug} in src/romledger/platforms.toml.",
        )
    ]


def _igir_checks(
    client: httpx.Client, throttle: http.Throttle, pinned: str, token: str | None
) -> list[Check]:
    return [
        _guarded(
            "igir:contract:release",
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
    response = _send(client, throttle, "GET", IGIR_RELEASE_URL, headers)
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
) -> httpx.Response:
    throttle.wait(url)
    try:
        response = client.request(method, url, headers=headers)
    except httpx.HTTPError as error:
        raise Inconclusive(_unreachable(url, error)) from error
    if (
        response.status_code in TRANSIENT_STATUSES
        or response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR
    ):
        raise Inconclusive(f"{url}: HTTP {response.status_code}")
    return response


def _unreachable(url: str, error: httpx.HTTPError) -> str:
    return f"{url}: request failed ({str(error) or type(error).__name__})"


def _is_challenge(response: httpx.Response) -> bool:
    if response.headers.get("cf-mitigated") == "challenge":
        return True
    if "text/html" not in response.headers.get("content-type", ""):
        return False
    text = response.text.lower()
    return any(marker in text for marker in CHALLENGE_MARKERS)
