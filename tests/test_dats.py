import os
from pathlib import Path

import httpx
import pytest

from rom_scraper import dats

BODY = b'clrmamepro (\n\tname "Nintendo"\n\tversion "2026.10.01"\n)\n'


def client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def serving(body: bytes) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, content=body))


def test_dat_path(tmp_path: Path) -> None:
    assert dats.dat_path(tmp_path, "no-intro/A - B") == tmp_path / "dats" / "no-intro" / "A - B.dat"


def test_url_encodes_spaces() -> None:
    assert dats.url("no-intro/A - B").endswith("/metadat/no-intro/A%20-%20B.dat")


def test_update_downloads_and_parses_version(tmp_path: Path) -> None:
    with client(serving(BODY)) as http_client:
        results = dats.update(tmp_path, {"nes": "no-intro/Nintendo"}, http_client)
    result = results["nes"]
    assert result.version == "2026.10.01"
    assert result.changed
    assert result.path.read_bytes() == BODY


def test_update_detects_unchanged(tmp_path: Path) -> None:
    with client(serving(BODY)) as http_client:
        dats.update(tmp_path, {"nes": "no-intro/Nintendo"}, http_client)
        again = dats.update(tmp_path, {"nes": "no-intro/Nintendo"}, http_client)
    assert not again["nes"].changed


def test_update_detects_changed(tmp_path: Path) -> None:
    with client(serving(BODY)) as http_client:
        dats.update(tmp_path, {"nes": "no-intro/Nintendo"}, http_client)
    with client(serving(BODY.replace(b"10.01", b"10.02"))) as http_client:
        again = dats.update(tmp_path, {"nes": "no-intro/Nintendo"}, http_client)
    assert again["nes"].changed
    assert again["nes"].version == "2026.10.02"


def test_missing_version_header(tmp_path: Path) -> None:
    with client(serving(b"no header")) as http_client:
        results = dats.update(tmp_path, {"nes": "no-intro/Nintendo"}, http_client)
    assert results["nes"].version == "unknown"


def test_http_404_error(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    with client(transport) as http_client, pytest.raises(dats.DatError) as error:
        dats.update(tmp_path, {"nes": "no-intro/Nope"}, http_client)
    message = str(error.value)
    assert "no-intro/Nope.dat: HTTP 404" in message
    assert "platforms.<slug>.dat" in message
    assert not (tmp_path / "dats").exists()


def test_transport_error(tmp_path: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with client(httpx.MockTransport(refuse)) as http_client, pytest.raises(dats.DatError) as error:
        dats.update(tmp_path, {"nes": "no-intro/Nintendo"}, http_client)
    assert "request failed (boom)" in str(error.value)
    assert "HTTPS_PROXY" in str(error.value)


def test_atomic_write_leaves_no_temp_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    with client(serving(BODY)) as http_client, pytest.raises(OSError, match="disk full"):
        dats.update(tmp_path, {"nes": "no-intro/Nintendo"}, http_client)
    assert list((tmp_path / "dats" / "no-intro").iterdir()) == []


def test_name_of_reads_header_name_or_falls_back_to_stem(tmp_path: Path) -> None:
    named = tmp_path / "A.dat"
    named.write_text('clrmamepro (\n\tname "Header Name"\n)\n')
    bare = tmp_path / "B.dat"
    bare.write_text("nothing")
    assert dats.name_of(named) == "Header Name"
    assert dats.name_of(bare) == "B"
