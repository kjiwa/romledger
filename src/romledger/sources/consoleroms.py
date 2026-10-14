import posixpath
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import httpx

from romledger import http
from romledger.sources.base import Candidate, Site
from romledger.sources.errors import SourceChanged
from romledger.titles import normalize

NAME = "consoleroms"
BASE_URL = "https://www.consoleroms.com"
HOSTS = ("www.consoleroms.com", "downloads.consoleroms.com")
MIN_GAP = http.DEFAULT_GAP
DOWNLOAD_PREFIX = "https://downloads.consoleroms.com/"
SUFFIXES = (".zip", ".7z")


@dataclass(frozen=True)
class Row:
    slug: str
    title: str


class _ListingParser(HTMLParser):
    def __init__(self, code: str) -> None:
        super().__init__()
        self._row = re.compile(rf"^/roms/{re.escape(code)}/([^/]+)$")
        self._page = re.compile(rf"^/roms/{re.escape(code)}/page/(\d+)$")
        self._href: str | None = None
        self._button = False
        self._text: list[str] = []
        self.rows: dict[str, Row] = {}
        self.pages = 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        values = dict(attrs)
        self._href = values.get("href") or ""
        self._button = values.get("role") == "button"
        self._text = []
        page = self._page.match(self._href)
        if page:
            self.pages = max(self.pages, int(page[1]))

    def handle_data(self, data: str) -> None:
        self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self._add_row()
            self._href = None

    def _add_row(self) -> None:
        match = self._row.match(self._href or "")
        title = "".join(self._text).strip()
        if match and title and not self._button and match[1] not in self.rows:
            self.rows[match[1]] = Row(match[1], title)


class _DownloadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.link: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = dict(attrs).get("href") or ""
        if tag == "a" and self.link is None and href.startswith(DOWNLOAD_PREFIX):
            self.link = href


def parse_listing(html: str, code: str, url: str) -> tuple[list[Row], int]:
    parser = _ListingParser(code)
    parser.feed(html)
    parser.close()
    if not parser.rows:
        raise SourceChanged(url, "no game rows found")
    return list(parser.rows.values()), parser.pages


def parse_download_link(html: str, url: str) -> str:
    parser = _DownloadParser()
    parser.feed(html)
    parser.close()
    if parser.link is None:
        raise SourceChanged(url, "no download link found")
    parts = urlsplit(parser.link)
    if not parts.path.lower().endswith(SUFFIXES):
        raise SourceChanged(url, f"unexpected download file type: {parts.path}")
    return urlunsplit(parts._replace(path=quote(unquote(parts.path))))


def pick(rows: list[Row], game: str) -> Row | None:
    wanted = normalize(game)
    same = [row for row in rows if wanted and normalize(row.title) == wanted]
    if len(same) > 1:
        print(
            f"romledger: warning: ambiguous: {game} matches {len(same)} ConsoleRoms rows; skipped",
            file=sys.stderr,
        )
    return same[0] if len(same) == 1 else None


class ConsoleromsSource:
    name = NAME

    def __init__(self, code: str, client: httpx.Client, throttle: http.Throttle) -> None:
        self._code = code
        self._site = Site(BASE_URL, HOSTS, MIN_GAP, client, throttle)
        self._rows: list[Row] | None = None

    def find(self, game: str) -> Candidate | None:
        row = pick(self._listing(), game)
        if row is None:
            return None
        url = f"{BASE_URL}/roms/{self._code}/{row.slug}/download"
        link = parse_download_link(self._site.get(url).text, url)
        suffix = posixpath.splitext(urlsplit(link).path)[1].lower()
        return Candidate(game, lambda: link, f"{game}{suffix}")

    def _listing(self) -> list[Row]:
        if self._rows is None:
            rows, pages = self._page(1)
            for number in range(2, pages + 1):
                rows += self._page(number)[0]
            self._rows = list({row.slug: row for row in rows}.values())
        return self._rows

    def _page(self, number: int) -> tuple[list[Row], int]:
        suffix = "" if number == 1 else f"/page/{number}"
        url = f"{BASE_URL}/roms/{self._code}{suffix}"
        return parse_listing(self._site.get(url).text, self._code, url)
