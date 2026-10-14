import threading
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from romledger.web import upload

from .support import Env


def post(env: Env, files: list[tuple[str, bytes]], follow_redirects: bool = True) -> httpx.Response:
    response: httpx.Response = env.client.post(
        "/inbox/upload",
        files=[("files", (name, data)) for name, data in files],
        follow_redirects=follow_redirects,
    )
    return response


def test_upload_saves_files_and_redirects(env: Env) -> None:
    response = post(env, [("a.nes", b"abc"), ("b.nes", b"defg")], follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/inbox?uploaded=2"
    assert (env.inbox / "a.nes").read_bytes() == b"abc"
    assert (env.inbox / "b.nes").read_bytes() == b"defg"
    assert not list(env.inbox.glob("*.part"))


def test_upload_json_for_scripts(env: Env) -> None:
    response = env.client.post(
        "/inbox/upload",
        files=[("files", ("a.nes", b"abc"))],
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == {"saved": [{"name": "a.nes", "size": 3}]}


def test_existing_names_get_a_free_suffix(env: Env) -> None:
    (env.inbox / "a.nes").write_bytes(b"old")
    response = env.client.post(
        "/inbox/upload",
        files=[("files", ("a.nes", b"new"))],
        headers={"Accept": "application/json"},
    )
    saved = response.json()["saved"][0]["name"]
    assert saved != "a.nes"
    assert (env.inbox / "a.nes").read_bytes() == b"old"
    assert (env.inbox / saved).read_bytes() == b"new"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a.nes", "a.nes"),
        ("../../etc/passwd", "passwd"),
        ("..\\..\\evil.bin", "evil.bin"),
        ("/abs/path/x.nes", "x.nes"),
        (".hidden", "hidden"),
        ("..", ""),
        ("dir/", ""),
        ("tab\tname\x00.nes", "tabname.nes"),
        ("  spaced.nes  ", "spaced.nes"),
        ("é" * 150, "é" * 100),
    ],
)
def test_safe_name(raw: str, expected: str) -> None:
    assert upload.safe_name(raw) == expected


def test_traversal_names_stay_inside_the_inbox(env: Env, tmp_path: Path) -> None:
    post(env, [("../../escape.nes", b"x")], follow_redirects=False)
    assert (env.inbox / "escape.nes").is_file()
    assert not (tmp_path / "escape.nes").exists()
    assert not (env.inbox.parent / "escape.nes").exists()


def test_parts_without_a_filename_are_ignored(env: Env) -> None:
    response = env.client.post(
        "/inbox/upload",
        data={"note": "hello"},
        files=[("files", ("a.nes", b"abc"))],
        headers={"Accept": "application/json"},
    )
    assert [item["name"] for item in response.json()["saved"]] == ["a.nes"]
    assert sorted(path.name for path in env.inbox.iterdir()) == ["a.nes"]


def test_empty_filename_is_not_saved(env: Env) -> None:
    response = env.client.post(
        "/inbox/upload",
        files=[("files", ("", b"abc"))],
        headers={"Accept": "application/json"},
    )
    assert response.json() == {"saved": []}
    assert list(env.inbox.iterdir()) == []


def test_non_multipart_is_refused(env: Env) -> None:
    response = env.client.post("/inbox/upload", json={"a": 1}, headers={"Accept": "text/html"})
    assert response.status_code == 415
    assert "multipart/form-data" in response.text
    missing = env.client.post(
        "/inbox/upload", content=b"x", headers={"Content-Type": "multipart/form-data"}
    )
    assert missing.status_code == 415


def test_truncated_body_keeps_nothing(env: Env) -> None:
    boundary = "XBOUND"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="files"; filename="a.nes"\r\n\r\n'
        "partial data with no closing boundary"
    ).encode()
    response = env.client.post(
        "/inbox/upload",
        content=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert response.status_code == 400
    assert "ended early" in response.text
    assert list(env.inbox.iterdir()) == []


def test_malformed_body_keeps_nothing(env: Env) -> None:
    boundary = "XBOUND"
    body = f"--{boundary}\r\nbroken header line without colon\r\n\r\ndata\r\n--{boundary}--\r\n"
    response = env.client.post(
        "/inbox/upload",
        content=body.encode(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert response.status_code == 400
    assert list(env.inbox.iterdir()) == []


def test_unwritable_inbox_is_reported(env: Env) -> None:
    env.inbox.chmod(0o500)
    try:
        response = env.client.post(
            "/inbox/upload", files=[("files", ("a.nes", b"abc"))], headers={"Accept": "text/html"}
        )
    finally:
        env.inbox.chmod(0o700)
    assert response.status_code == 500
    assert "cannot write to" in response.text


def test_large_upload_streams_to_disk(env: Env) -> None:
    payload = b"\x00" * (5 * 1024 * 1024)
    response = env.client.post(
        "/inbox/upload",
        files=[("files", ("big.bin", payload))],
        headers={"Accept": "application/json"},
    )
    assert response.json()["saved"][0]["size"] == len(payload)
    assert (env.inbox / "big.bin").stat().st_size == len(payload)


def test_abort_removes_the_partial_file(tmp_path: Path) -> None:
    receiver = upload.Receiver(tmp_path)
    receiver._headers = {b"content-disposition": b'form-data; name="files"; filename="a.nes"'}
    receiver._headers_finished()
    receiver._data(b"abcdef", 0, 6)
    assert (tmp_path / "a.nes.part").exists()
    receiver.abort()
    receiver.abort()
    assert list(tmp_path.iterdir()) == []


def test_other_clients_cannot_reach_upload_without_auth(env: Env) -> None:
    response = TestClient(env.client.app).post("/inbox/upload", files=[("files", ("a", b"b"))])
    assert response.status_code == 401
    assert list(env.inbox.iterdir()) == []


def test_upload_is_refused_while_a_job_runs(env: Env) -> None:
    release = threading.Event()
    env.services.jobs.start("scan", lambda: release.wait(5))
    try:
        response = env.client.post(
            "/inbox/upload",
            files=[("files", ("a.nes", b"abc"))],
            headers={"Accept": "application/json"},
        )
    finally:
        release.set()
        env.services.jobs.wait(5)
    assert response.status_code == 409
    assert "scan is running" in response.text
    assert list(env.inbox.iterdir()) == []


def test_names_ending_in_part_are_refused(env: Env) -> None:
    response = post(env, [("ok.nes", b"1"), ("game.nes.part", b"2")])
    assert response.status_code == 400
    assert ".part" in response.text
    assert not list(env.inbox.glob("*.part"))
