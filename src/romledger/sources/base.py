import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from romledger import http
from romledger.sources.errors import FetchError

CHUNK = 1 << 16
PARTIAL = ".part"


@dataclass(frozen=True)
class Candidate:
    game: str
    url_resolver: Callable[[], str]
    filename: str
    size: int | None = None
    md5: str | None = None


class Source(Protocol):
    name: str

    def find(self, game: str) -> Candidate | None: ...


class Site:
    def __init__(
        self,
        base_url: str,
        hosts: tuple[str, ...],
        min_gap: float,
        client: httpx.Client,
        throttle: http.Throttle,
    ) -> None:
        self._base_url = base_url
        self._hosts = hosts
        self._min_gap = min_gap
        self._client = client
        self._throttle = throttle
        self._robots: http.Robots | None = None
        self._set_gap(min_gap)

    def get(self, url: str, expect: tuple[int, ...] = (httpx.codes.OK,)) -> httpx.Response:
        robots = self._load_robots()
        http.require_allowed(robots, url)
        self._throttle.wait(url)
        response = self._client.get(url)
        if response.status_code not in expect:
            raise FetchError(f"{url}: HTTP {response.status_code}")
        return response

    def _load_robots(self) -> http.Robots:
        if self._robots is None:
            self._robots = http.load_robots(self._base_url, self._client, self._throttle)
            self._set_gap(max(self._min_gap, self._robots.crawl_delay))
        return self._robots

    def _set_gap(self, seconds: float) -> None:
        for host in self._hosts:
            self._throttle.set_gap(host, seconds)


def fetch_to(
    inbox: Path, candidate: Candidate, client: httpx.Client, throttle: http.Throttle
) -> Path:
    name = _safe_name(candidate.filename)
    final = inbox / name
    part = inbox / f"{name}{PARTIAL}"
    inbox.mkdir(parents=True, exist_ok=True)
    url = candidate.url_resolver()
    offset = part.stat().st_size if part.is_file() else 0
    throttle.wait(url)
    headers = {"Accept-Encoding": "identity"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    with client.stream("GET", url, headers=headers) as response:
        resumed = _check_response(response, url, offset, part)
        expected = _expected_size(response, offset if resumed else 0, candidate)
        with part.open("ab" if resumed else "wb") as handle:
            for chunk in response.iter_bytes(CHUNK):
                handle.write(chunk)
    _verify(part, name, expected, candidate.md5)
    os.replace(part, final)
    return final


def _safe_name(filename: str) -> str:
    if not filename or filename in (".", "..") or "/" in filename or "\\" in filename:
        raise FetchError(f"refusing unsafe file name {filename!r}")
    return filename


def _check_response(response: httpx.Response, url: str, offset: int, part: Path) -> bool:
    status = response.status_code
    if status == httpx.codes.REQUESTED_RANGE_NOT_SATISFIABLE:
        part.unlink(missing_ok=True)
        raise FetchError(f"{url}: partial file no longer valid; removed it, run fetch again")
    if status not in (httpx.codes.OK, httpx.codes.PARTIAL_CONTENT):
        raise FetchError(f"{url}: HTTP {status}")
    if status == httpx.codes.PARTIAL_CONTENT:
        if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
            part.unlink(missing_ok=True)
            raise FetchError(f"{url}: server resumed at the wrong offset; removed the partial file")
        return True
    return False


def _expected_size(response: httpx.Response, offset: int, candidate: Candidate) -> int | None:
    length = response.headers.get("Content-Length", "")
    return offset + int(length) if length.isdigit() else candidate.size


def _verify(part: Path, name: str, expected: int | None, md5: str | None) -> None:
    size = part.stat().st_size
    if expected is not None and size != expected:
        part.unlink()
        raise FetchError(f"{name}: downloaded {size} bytes, expected {expected}; removed it")
    if md5 is not None and _md5(part) != md5.lower():
        part.unlink()
        raise FetchError(f"{name}: md5 does not match the source listing; removed it")


def _md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
