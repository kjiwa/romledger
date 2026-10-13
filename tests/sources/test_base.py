import hashlib
from pathlib import Path

import httpx
import pytest

from conftest import FakeThrottle
from romledger import http
from romledger.sources.base import Candidate, Site, fetch_to
from romledger.sources.errors import FetchError, SourceBlocked, SourceChanged

URL = "https://dl.example/roms/Game.zip"
BODY = b"0123456789"


def candidate(
    filename: str = "Game (USA).zip", size: int | None = None, md5: str | None = None
) -> Candidate:
    return Candidate("Game (USA)", lambda: URL, filename, size, md5)


def make_client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def serve(response: httpx.Response, seen: list[httpx.Request] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return response

    return make_client(httpx.MockTransport(handler))


def run(inbox: Path, client: httpx.Client, cand: Candidate | None = None) -> Path:
    return fetch_to(inbox, cand or candidate(), client, http.Throttle(0.0))


def test_fetch_writes_final_file_atomically(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    final = run(tmp_path, serve(httpx.Response(200, content=BODY), seen))
    assert final == tmp_path / "Game (USA).zip"
    assert final.read_bytes() == BODY
    assert sorted(path.name for path in tmp_path.iterdir()) == ["Game (USA).zip"]
    assert "Range" not in seen[0].headers


def test_fetch_resumes_a_partial_file(tmp_path: Path) -> None:
    (tmp_path / "Game (USA).zip.part").write_bytes(BODY[:4])
    seen: list[httpx.Request] = []
    response = httpx.Response(206, content=BODY[4:], headers={"Content-Range": "bytes 4-9/10"})
    final = run(tmp_path, serve(response, seen))
    assert seen[0].headers["Range"] == "bytes=4-"
    assert final.read_bytes() == BODY
    assert not (tmp_path / "Game (USA).zip.part").exists()


def test_fetch_restarts_when_the_server_ignores_range(tmp_path: Path) -> None:
    (tmp_path / "Game (USA).zip.part").write_bytes(b"stale")
    final = run(tmp_path, serve(httpx.Response(200, content=BODY)))
    assert final.read_bytes() == BODY


def test_fetch_rejects_a_resume_at_the_wrong_offset(tmp_path: Path) -> None:
    part = tmp_path / "Game (USA).zip.part"
    part.write_bytes(BODY[:4])
    response = httpx.Response(206, content=BODY[2:], headers={"Content-Range": "bytes 2-9/10"})
    with pytest.raises(FetchError, match="wrong offset"):
        run(tmp_path, serve(response))
    assert not part.exists()


def test_fetch_discards_an_unsatisfiable_partial(tmp_path: Path) -> None:
    part = tmp_path / "Game (USA).zip.part"
    part.write_bytes(BODY)
    with pytest.raises(FetchError, match="run fetch again"):
        run(tmp_path, serve(httpx.Response(416)))
    assert not part.exists()


@pytest.mark.parametrize("status", [403, 404, 500])
def test_fetch_http_error_leaves_nothing(tmp_path: Path, status: int) -> None:
    with pytest.raises(FetchError, match=f"HTTP {status}"):
        run(tmp_path, serve(httpx.Response(status)))
    assert list(tmp_path.iterdir()) == []


def test_fetch_size_mismatch_removes_the_partial(tmp_path: Path) -> None:
    response = httpx.Response(200, content=BODY[:5], headers={"Content-Length": "10"})
    with pytest.raises(FetchError, match="downloaded 5 bytes, expected 10"):
        run(tmp_path, serve(response))
    assert list(tmp_path.iterdir()) == []


def test_fetch_size_falls_back_to_the_listing(tmp_path: Path) -> None:
    response = httpx.Response(200, content=BODY, headers={"Content-Length": "x"})
    with pytest.raises(FetchError, match="expected 99"):
        run(tmp_path, serve(response), candidate(size=99))
    assert list(tmp_path.iterdir()) == []


def test_fetch_checks_md5(tmp_path: Path) -> None:
    md5 = hashlib.md5(BODY, usedforsecurity=False).hexdigest().upper()
    final = run(tmp_path, serve(httpx.Response(200, content=BODY)), candidate(md5=md5))
    assert final.read_bytes() == BODY


def test_fetch_md5_mismatch_removes_the_file(tmp_path: Path) -> None:
    with pytest.raises(FetchError, match="md5 does not match"):
        run(tmp_path, serve(httpx.Response(200, content=BODY)), candidate(md5="0" * 32))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "filename", ["../Game.zip", "a/Game.zip", "a\\Game.zip", "..", ".", "", "/etc/passwd"]
)
def test_fetch_refuses_unsafe_filenames(tmp_path: Path, filename: str) -> None:
    seen: list[httpx.Request] = []
    with pytest.raises(FetchError, match="unsafe file name"):
        run(tmp_path, serve(httpx.Response(200, content=BODY), seen), candidate(filename))
    assert seen == []
    assert list(tmp_path.iterdir()) == []


def test_fetch_keeps_dots_inside_names(tmp_path: Path) -> None:
    final = run(tmp_path, serve(httpx.Response(200, content=BODY)), candidate("Mr. Do..zip"))
    assert final.name == "Mr. Do..zip"


def test_fetch_waits_on_the_throttle(tmp_path: Path, fake_throttle: FakeThrottle) -> None:
    throttle, sleeps = fake_throttle(5.0)
    throttle.wait(URL)
    fetch_to(tmp_path, candidate(), serve(httpx.Response(200, content=BODY)), throttle)
    assert sleeps == [5.0]


def site_client(robots: str, pages: dict[str, httpx.Response], seen: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        return pages.get(request.url.path, httpx.Response(404))

    return make_client(httpx.MockTransport(handler))


def test_site_loads_robots_once_and_applies_crawl_delay(fake_throttle: FakeThrottle) -> None:
    seen: list[str] = []
    throttle, sleeps = fake_throttle(0.0)
    client = site_client(
        "User-agent: *\nCrawl-delay: 20\n",
        {"/a": httpx.Response(200), "/b": httpx.Response(200)},
        seen,
    )
    site = Site("https://a.example", ("a.example",), 10.0, client, throttle)
    site.get("https://a.example/a")
    site.get("https://a.example/b")
    assert seen == ["/robots.txt", "/a", "/b"]
    assert sleeps == [20.0, 20.0]


def test_site_minimum_gap_beats_a_shorter_crawl_delay(fake_throttle: FakeThrottle) -> None:
    throttle, sleeps = fake_throttle(0.0)
    client = site_client("User-agent: *\nCrawl-delay: 2\n", {"/a": httpx.Response(200)}, [])
    Site("https://a.example", ("a.example",), 10.0, client, throttle).get("https://a.example/a")
    assert sleeps == [10.0]


def test_site_refuses_disallowed_urls(fake_throttle: FakeThrottle) -> None:
    seen: list[str] = []
    client = site_client("User-agent: *\nDisallow: /admin/\n", {}, seen)
    site = Site("https://a.example", ("a.example",), 0.0, client, fake_throttle(0.0)[0])
    with pytest.raises(SourceBlocked, match=r"https://a\.example/admin/x"):
        site.get("https://a.example/admin/x")
    assert seen == ["/robots.txt"]


def test_site_unexpected_status(fake_throttle: FakeThrottle) -> None:
    client = site_client("", {}, [])
    site = Site("https://a.example", ("a.example",), 0.0, client, fake_throttle(0.0)[0])
    with pytest.raises(FetchError, match=r"https://a.example/x: HTTP 404"):
        site.get("https://a.example/x")
    assert site.get("https://a.example/x", expect=(404,)).status_code == 404


def test_source_changed_message_names_the_url() -> None:
    message = str(SourceChanged("https://a.example/x", "no rows"))
    assert message.startswith("https://a.example/x: no rows.")
