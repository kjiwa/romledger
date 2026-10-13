from typing import Any
from urllib.parse import quote

import httpx

from romledger import http
from romledger.sources.base import Candidate, Site
from romledger.sources.errors import SourceChanged

NAME = "internet-archive"
BASE_URL = "https://archive.org"
HOSTS = ("archive.org",)


class InternetArchiveSource:
    name = NAME

    def __init__(self, item: str, client: httpx.Client, throttle: http.Throttle) -> None:
        self._item = item
        self._site = Site(BASE_URL, HOSTS, http.DEFAULT_GAP, client, throttle)
        self._files: dict[str, dict[str, Any]] | None = None

    def find(self, game: str) -> Candidate | None:
        entry = self._listing().get(f"{game}.zip")
        if entry is None:
            return None
        url = f"{BASE_URL}/download/{self._item}/{quote(entry['name'], safe='/')}"
        size = str(entry.get("size", ""))
        md5 = entry.get("md5")
        return Candidate(
            game,
            lambda: url,
            entry["name"].rsplit("/", 1)[-1],
            int(size) if size.isdigit() else None,
            md5 if isinstance(md5, str) else None,
        )

    def _listing(self) -> dict[str, dict[str, Any]]:
        if self._files is None:
            url = f"{BASE_URL}/metadata/{self._item}"
            self._files = _index(self._site.get(url), url, self._item)
        return self._files


def _index(response: httpx.Response, url: str, item: str) -> dict[str, dict[str, Any]]:
    try:
        files = response.json().get("files")
    except (ValueError, AttributeError) as error:
        raise SourceChanged(url, "response is not the expected JSON object") from error
    if not isinstance(files, list) or not files:
        raise SourceChanged(url, f"no files listed for item {item!r}")
    index: dict[str, dict[str, Any]] = {}
    for entry in files:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            index.setdefault(entry["name"].rsplit("/", 1)[-1], entry)
    return index
