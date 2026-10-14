import dataclasses
import threading

from fastapi.testclient import TestClient

from romledger import config, state
from romledger.context import Context
from romledger.web import app as web_app

from .support import TOKEN, Env, seed


def test_platforms_before_and_after_a_scan(env: Env) -> None:
    before = env.client.get("/api/platforms").json()
    assert before[0]["slug"] == "nes"
    assert before[0]["scanned_at"] is None
    assert before[0]["wanted"] is None
    seed(env.context)
    after = env.client.get("/api/platforms").json()[0]
    assert (after["have"], after["inbox"], after["missing"], after["wanted"]) == (1, 1, 1, 3)
    assert after["percent"] == 33
    assert after["sites"] == {
        "vimm": "NES",
        "coolrom": None,
        "consoleroms": "nes",
        "emuland": "consoles/dendy",
        "archive_item": None,
    }


def test_platform_sites_report_configured_codes(env: Env) -> None:
    nes = env.context.config.platforms["nes"]
    env.context.config.platforms["nes"] = dataclasses.replace(
        nes, coolrom="NES", archive_item="item-1"
    )
    env.context.platforms.pop("nes")
    sites = env.client.get("/api/platforms").json()[0]["sites"]
    assert sites == {
        "vimm": None,
        "coolrom": "NES",
        "consoleroms": None,
        "emuland": None,
        "archive_item": "item-1",
    }


def test_missing_lists_games_with_links(env: Env) -> None:
    seed(env.context)
    body = env.client.get("/api/platforms/nes/missing").json()
    assert body["total"] == 1
    assert body["games"][0]["game"] == "Beta (USA)"
    assert body["games"][0]["links"] == {
        "vimm": "https://vimm.net/vault/?p=list&system=NES&q=Beta",
        "emuland": "https://www.emu-land.net/en/search_games?q=Beta",
    }
    assert env.client.get("/api/platforms/nes/missing?q=zzz").json()["games"] == []
    assert env.client.get("/api/platforms/nes/missing?limit=0").status_code == 422


def test_missing_errors(env: Env) -> None:
    assert env.client.get("/api/platforms/nope/missing").status_code == 404
    unscanned = env.client.get("/api/platforms/nes/missing")
    assert unscanned.status_code == 409
    assert "romledger scan" in unscanned.json()["detail"]


def test_lookup_by_hash(env: Env) -> None:
    seed(env.context)
    found = env.client.get("/api/lookup", params={"sha1": "B" * 40}).json()["matches"]
    assert found == [{"platform": "nes", "game": "Beta (USA)", "state": "missing", "exact": True}]
    unwanted = env.client.get("/api/lookup", params={"sha1": "d" * 40}).json()["matches"]
    assert unwanted[0]["state"] == "unwanted"
    unknown = env.client.get("/api/lookup", params={"sha1": "9" * 40}).json()["matches"]
    assert unknown[0]["state"] == "unknown"


def test_lookup_by_name(env: Env) -> None:
    seed(env.context)
    exact = env.client.get("/api/lookup", params={"name": "Cat (USA)", "platform": "nes"})
    assert exact.json()["matches"][0]["state"] == "inbox"
    approximate = env.client.get("/api/lookup", params={"name": "Cat", "platform": "nes"})
    assert approximate.json()["matches"][0]["exact"] is False


def test_lookup_name_with_no_single_answer_lists_every_candidate(env: Env) -> None:
    seed(env.context)
    path = env.context.data_dir / "state.db"
    with state.State(path) as database:
        database.replace_index(
            "nes",
            [],
            [
                state.IndexedGame("Dup (USA)", "dup", "usa"),
                state.IndexedGame("Dup (USA) (B)", "dup", "usa"),
            ],
            state.DatStamp("2", 0, 0),
        )
    response = env.client.get("/api/lookup", params={"name": "Dup", "platform": "nes"})
    assert [match["game"] for match in response.json()["matches"]] == ["Dup (USA)", "Dup (USA) (B)"]


def test_lookup_name_regions_narrow_the_candidates(env: Env) -> None:
    seed(env.context)
    path = env.context.data_dir / "state.db"
    with state.State(path) as database:
        database.replace_index(
            "nes",
            [],
            [
                state.IndexedGame("Dup (USA, Europe)", "dup", "usa"),
                state.IndexedGame("Dup (Japan)", "dup", "japan"),
            ],
            state.DatStamp("2", 0, 0),
        )
    params = {"name": "Dup", "platform": "nes", "regions": "Japan,Brazil"}
    response = env.client.get("/api/lookup", params=params)
    assert [match["game"] for match in response.json()["matches"]] == ["Dup (Japan)"]


def test_lookup_name_is_length_limited(env: Env) -> None:
    response = env.client.get("/api/lookup", params={"name": "x" * 301, "platform": "nes"})
    assert response.status_code == 422


def test_lookup_argument_errors(env: Env) -> None:
    assert env.client.get("/api/lookup").status_code == 422
    both = env.client.get("/api/lookup", params={"sha1": "a" * 40, "name": "x"})
    assert both.status_code == 422
    assert env.client.get("/api/lookup", params={"sha1": "xyz"}).status_code == 422
    no_platform = env.client.get("/api/lookup", params={"name": "x"})
    assert no_platform.status_code == 422
    assert "platform" in no_platform.json()["detail"]
    unknown = env.client.get("/api/lookup", params={"name": "x", "platform": "nope"})
    assert unknown.status_code == 404


def test_scan_and_import_run_as_jobs(env: Env) -> None:
    assert env.client.get("/api/jobs/current").json() == {"job": None}
    started = env.client.post("/api/scan")
    assert started.status_code == 202
    assert started.json()["kind"] == "scan"
    env.services.jobs.wait(5)
    assert env.reports
    assert env.client.get("/api/jobs/current").json() == {"job": None}
    assert env.client.post("/api/import").status_code == 202
    env.services.jobs.wait(5)
    assert [record.kind for record in env.services.jobs.history()] == ["import", "scan"]
    assert all(record.ok for record in env.services.jobs.history())


def test_a_second_job_is_refused_while_one_runs(env: Env) -> None:
    release = threading.Event()
    env.services.jobs.start("scan", lambda: release.wait(5) or True)
    try:
        busy = env.client.post("/api/import")
        assert busy.status_code == 409
        assert "scan is already running" in busy.json()["detail"]
        assert env.client.get("/api/jobs/current").json()["job"]["kind"] == "scan"
    finally:
        release.set()
        env.services.jobs.wait(5)


def test_actions_need_platforms_and_dats(env: Env) -> None:
    env.context.config.platforms.clear()
    none = env.client.post("/api/scan")
    assert none.status_code == 400
    assert "no platforms configured" in none.json()["detail"]


def test_actions_need_a_downloaded_dat(env: Env) -> None:
    for path in env.data.rglob("*.dat"):
        path.unlink()
    response = env.client.post("/api/scan")
    assert response.status_code == 400
    assert "dats update" in response.json()["detail"]


def test_unmounted_library_is_a_503(env: Env) -> None:
    def broken() -> Context:
        raise config.ConfigError("roms is not mounted")

    client = TestClient(web_app.create_app(broken, TOKEN), headers=env.bearer())
    api = client.get("/api/platforms")
    assert api.status_code == 503
    assert api.json()["detail"] == "roms is not mounted"
    page = client.get("/")
    assert page.status_code == 503
    assert "roms is not mounted" in page.text
