import functools
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser

import httpx

from romledger import http
from romledger.sources.base import Candidate, Site
from romledger.sources.errors import SourceChanged

NAME = "coolrom"
BASE_URL = "https://coolrom.com"
HOSTS = ("coolrom.com", "dl.coolrom.com")
MIN_GAP = 10.0
TAGS = re.compile(r"\([^)]*\)")
FIRST_TAG = re.compile(r"\(([^),]*)")
NOT_ALNUM = re.compile(r"[^a-z0-9]+")
ASSIGNMENT = re.compile(r'getElementById\("dl"\)\.innerHTML\s*=\s*("(?:[^"\\]|\\.)*");')
SIGNED_LINK = re.compile(r'href="(https://dl\.coolrom\.com/[^"]+)"')


@dataclass(frozen=True)
class Row:
    id: str
    title: str
    region: str


class _SectionParser(HTMLParser):
    def __init__(self, code: str) -> None:
        super().__init__()
        self._row = re.compile(rf"^/roms/{re.escape(code)}/(\d+)/[^/]+\.php$")
        self._platform_link = f"/roms/{code}/"
        self._classes: list[str] = []
        self._href: str | None = None
        self._text: list[str] = []
        self.rows: list[Row] = []
        self.has_header = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "div":
            self._classes.append(values.get("class") or "")
        elif tag == "a":
            self._href = values.get("href")
            self._text = []
            self.has_header = self.has_header or self._href == self._platform_link

    def handle_data(self, data: str) -> None:
        self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._classes:
            self._classes.pop()
        elif tag == "a" and self._href is not None:
            self._add_row()
            self._href = None

    def _add_row(self) -> None:
        match = self._row.match(self._href or "")
        if match and self._classes and self._classes[-1]:
            self.rows.append(Row(match[1], "".join(self._text).strip(), self._classes[-1]))


def normalize(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", TAGS.sub("", title)).lower()
    return NOT_ALNUM.sub("", ascii_title)


def letter_of(title: str) -> str | None:
    decomposed = unicodedata.normalize("NFKD", title).lower()
    first = next(
        (char for char in decomposed if char in "abcdefghijklmnopqrstuvwxyz0123456789"), None
    )
    return None if first is None else ("0" if first.isdigit() else first)


def region_of(game: str) -> str | None:
    match = FIRST_TAG.search(game)
    if match is None:
        return None
    region = match[1].strip().lower()
    return "usa" if region == "world" else region


def parse_section(html: str, code: str, url: str) -> list[Row]:
    parser = _SectionParser(code)
    parser.feed(html)
    parser.close()
    if not parser.rows and not parser.has_header:
        raise SourceChanged(url, "no game rows or breadcrumb found")
    return parser.rows


def parse_signed_link(html: str, url: str) -> str:
    for assignment in ASSIGNMENT.finditer(html):
        try:
            link = SIGNED_LINK.search(json.loads(assignment[1]))
        except ValueError as error:
            raise SourceChanged(url, "download script is not a JSON string") from error
        if link:
            return link[1]
    raise SourceChanged(url, "no download link found")


def pick(rows: list[Row], game: str) -> Row | None:
    same = [row for row in rows if normalize(row.title) == normalize(game)]
    region = region_of(game)
    pool = [row for row in same if row.region.lower() == region] or same
    if len(pool) > 1:
        print(
            f"romledger: warning: ambiguous: {game} matches {len(pool)} CoolROM rows; skipped",
            file=sys.stderr,
        )
    return pool[0] if len(pool) == 1 else None


class CoolromSource:
    name = NAME

    def __init__(self, code: str, client: httpx.Client, throttle: http.Throttle) -> None:
        self._code = code
        self._site = Site(BASE_URL, HOSTS, MIN_GAP, client, throttle)
        self._sections: dict[str, list[Row]] = {}

    def find(self, game: str) -> Candidate | None:
        letter = letter_of(game)
        if letter is None:
            return None
        row = pick(self._section(letter), game)
        if row is None:
            return None
        return Candidate(game, functools.partial(self.resolve, row.id), f"{game}.zip")

    def resolve(self, row_id: str) -> str:
        url = f"{BASE_URL}/dlpop.php?id={row_id}"
        return parse_signed_link(self._site.get(url).text, url)

    def _section(self, letter: str) -> list[Row]:
        if letter not in self._sections:
            url = f"{BASE_URL}/roms/{self._code}/{letter}/"
            response = self._site.get(url, expect=(httpx.codes.OK, httpx.codes.NOT_FOUND))
            if response.status_code == httpx.codes.NOT_FOUND:
                self._sections[letter] = []
            else:
                self._sections[letter] = parse_section(response.text, self._code, url)
        return self._sections[letter]
