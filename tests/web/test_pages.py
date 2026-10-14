import threading
from pathlib import Path

from romledger import state

from .support import SCANNED_AT, Env, seed


def test_overview_before_a_scan_points_to_scanning(env: Env) -> None:
    page = env.client.get("/")
    assert page.status_code == 200
    assert "<h1>" in page.text
    assert "Nothing scanned yet" in page.text
    assert "33%" not in page.text


def test_overview_lists_progress_per_platform(env: Env) -> None:
    seed(env.context)
    page = env.client.get("/")
    assert "Nintendo Entertainment System" in page.text
    assert "33%" in page.text
    assert 'href="/platforms/nes"' in page.text


def test_platform_page_filters_and_links(env: Env) -> None:
    seed(env.context)
    missing = env.client.get("/platforms/nes")
    assert "Beta (USA)" in missing.text
    assert "Alpha (USA)" not in missing.text
    assert "https://vimm.net/vault/" in missing.text
    assert "https://www.emu-land.net/en/search_games?q=Beta" in missing.text
    assert "archive.org" not in missing.text
    have = env.client.get("/platforms/nes?state=have")
    assert "Alpha (USA)" in have.text
    everything = env.client.get("/platforms/nes?state=all")
    assert all(name in everything.text for name in ("Alpha", "Beta", "Cat"))
    assert "No games match." in env.client.get("/platforms/nes?q=zzz").text


def test_platform_page_paginates(env: Env) -> None:
    items = [state.Item(f"Game {n:03d} (USA)", "missing", None) for n in range(250)]
    with state.State(env.data / "state.db") as database:
        database.replace_platform("nes", items, [], "1", SCANNED_AT)
    first = env.client.get("/platforms/nes?q=Game")
    assert "offset=200" in first.text
    second = env.client.get("/platforms/nes?q=Game&offset=200")
    assert "Game 249 (USA)" in second.text
    assert "offset=0" in second.text
    assert "offset=400" not in second.text


def test_platform_page_errors(env: Env) -> None:
    assert env.client.get("/platforms/nope").status_code == 404
    bad = env.client.get("/platforms/nes?state=bogus")
    assert bad.status_code == 422
    assert "state" in bad.text
    assert env.client.get("/platforms/nes?offset=-1").status_code == 422


def test_inbox_lists_files_and_hides_junk(env: Env) -> None:
    (env.inbox / "a.nes").write_bytes(b"x" * 2048)
    (env.inbox / ".DS_Store").write_bytes(b"")
    (env.inbox / "._a.nes").write_bytes(b"")
    (env.inbox / "b.nes.part").write_bytes(b"")
    (env.inbox / "unmatched").mkdir()
    (env.inbox / "unmatched" / "x.bin").write_bytes(b"")
    (env.inbox / "unwanted").mkdir()
    (env.inbox / "unwanted" / "y.bin").write_bytes(b"")
    (env.inbox / "sub").mkdir()
    (env.inbox / "sub" / "c.nes").write_bytes(b"")
    page = env.client.get("/inbox")
    assert "a.nes" in page.text
    assert "2.0 KB" in page.text
    assert "uploading" in page.text
    assert str(Path("sub") / "c.nes") in page.text
    assert ".DS_Store" not in page.text
    assert "x.bin" not in page.text
    assert "y.bin" not in page.text
    assert "<dt>Unwanted</dt><dd>1</dd>" in page.text


def test_empty_inbox_and_upload_notice(env: Env) -> None:
    assert "inbox is empty" in env.client.get("/inbox").text
    assert "Uploaded 1 file." in env.client.get("/inbox?uploaded=1").text
    assert "Uploaded 3 files." in env.client.get("/inbox?uploaded=3").text


def test_activity_shows_job_history(env: Env) -> None:
    assert env.client.get("/activity").status_code == 200
    started = env.client.post("/scan", follow_redirects=False)
    assert started.status_code == 303
    assert started.headers["location"] == "/activity"
    env.services.jobs.wait(5)
    page = env.client.get("/activity")
    assert "scan" in page.text.lower()


def test_import_form_redirects_to_activity(env: Env) -> None:
    response = env.client.post("/import", follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, "/activity")
    env.services.jobs.wait(5)


def test_busy_form_post_shows_an_error_page(env: Env) -> None:
    release = threading.Event()
    env.services.jobs.start("scan", lambda: release.wait(5) or True)
    try:
        page = env.client.post("/scan")
        assert page.status_code == 409
        assert "already running" in page.text
        assert "meta http-equiv" in env.client.get("/").text
        assert "Scanning" in env.client.get("/").text
        assert "meta http-equiv" not in env.client.get("/inbox").text
    finally:
        release.set()
        env.services.jobs.wait(5)


def test_unknown_path_is_a_404_page(env: Env) -> None:
    page = env.client.get("/nope")
    assert page.status_code == 404
    assert "Not found" in page.text


def test_inbox_skips_files_that_vanish_or_are_broken_links(env: Env) -> None:
    (env.inbox / "a.nes").write_bytes(b"x")
    (env.inbox / "dangling.nes").symlink_to(env.inbox / "gone.nes")
    page = env.client.get("/inbox")
    assert page.status_code == 200
    assert "a.nes" in page.text
    assert "dangling.nes" not in page.text
