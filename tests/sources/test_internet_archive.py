import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from romledger import http
from romledger.sources import internet_archive
from romledger.sources.errors import SourceChanged

ITEM = "No-Intro_NES"
METADATA_PATH = f"/metadata/{ITEM}"


class Archive:
    def __init__(self, body: str, status: int = 200) -> None:
        self.requests: list[str] = []
        self._metadata = httpx.Response(status, text=body)

    def source(self) -> internet_archive.InternetArchiveSource:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request.url.path)
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /control/\n")
            return self._metadata

        client = httpx.Client(transport=httpx.MockTransport(handler))
        return internet_archive.InternetArchiveSource(
            ITEM, client, http.Throttle(sleep=lambda _: None)
        )


@pytest.fixture
def archive(fixtures: Path) -> Archive:
    return Archive((fixtures / "archive" / "metadata.json").read_text())


def test_find_exact_name(archive: Archive) -> None:
    candidate = archive.source().find("1943 - The Battle of Midway (USA)")
    assert candidate is not None
    assert candidate.filename == "1943 - The Battle of Midway (USA).zip"
    assert candidate.url_resolver() == (
        f"https://archive.org/download/{ITEM}/1943%20-%20The%20Battle%20of%20Midway%20%28USA%29.zip"
    )
    assert candidate.size is not None
    assert candidate.md5 is not None
    assert len(candidate.md5) == 32


def test_find_requires_an_exact_match(archive: Archive) -> None:
    source = archive.source()
    assert source.find("1943 - The Battle of Midway") is None
    assert source.find("1943 - the battle of midway (USA)") is None
    assert source.find("No-Intro_NES_files") is None


def test_metadata_is_loaded_once(archive: Archive) -> None:
    source = archive.source()
    source.find("a")
    source.find("b")
    assert archive.requests == ["/robots.txt", METADATA_PATH]


@pytest.mark.parametrize("body", ["{}", '{"files": []}', "[]", "not json", '{"files": 3}'])
def test_unexpected_metadata_is_source_changed(body: str) -> None:
    with pytest.raises(SourceChanged, match=r"No-Intro_NES|JSON"):
        Archive(body).source().find("x")


def test_entries_without_size_or_md5() -> None:
    files: list[Any] = [{"name": "A (USA).zip"}, {"name": "B (USA).zip", "size": 5, "md5": 7}, 3]
    source = Archive(json.dumps({"files": files})).source()
    bare = source.find("A (USA)")
    assert bare is not None
    assert (bare.size, bare.md5) == (None, None)
    numeric = source.find("B (USA)")
    assert numeric is not None
    assert (numeric.size, numeric.md5) == (5, None)


@pytest.mark.live
def test_live_metadata() -> None:
    with http.client() as client:
        source = internet_archive.InternetArchiveSource(ITEM, client, http.Throttle())
        assert source.find("Super Mario Bros. (World)") is not None
