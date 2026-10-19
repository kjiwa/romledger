import asyncio
import dataclasses
import os
import threading
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from romledger import igir
from romledger.config import ConfigError
from romledger.context import Context
from romledger.web import actions, watch
from romledger.web import app as web_app

from .support import TOKEN, Env


def poller(env: Env) -> watch.Watcher:
    return watch.Watcher(env.services)


def put(path: Path, size: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_snapshot_skips_set_aside_junk_and_partial_files(tmp_path: Path) -> None:
    first, second = tmp_path / "one", tmp_path / "two"
    put(first / "a.zip", 3)
    put(first / "sub" / "b.nes", 2)
    put(second / "c.nes")
    for ignored in (
        "unmatched/x.nes",
        "unwanted/x.nes",
        "duplicates/x.nes",
        ".DS_Store",
        "._a.zip",
        "a.zip.part",
        "a.zip.crdownload",
        "a.zip.download",
    ):
        put(first / ignored)
    (first / "dangling").symlink_to(first / "missing")
    found = watch.snapshot([first, second])
    assert {name: size for name, (size, _) in found.items()} == {
        str(first / "a.zip"): 3,
        str(first / "sub" / "b.nes"): 2,
        str(second / "c.nes"): 1,
    }


def test_snapshot_keeps_nested_folders_named_like_set_aside_dirs(tmp_path: Path) -> None:
    put(tmp_path / "sub" / "unmatched" / "a.nes")
    assert list(watch.snapshot([tmp_path])) == [str(tmp_path / "sub" / "unmatched" / "a.nes")]


def quiet(watcher: watch.Watcher) -> None:
    assert [watcher.poll(), watcher.poll()] == [False, False]


def test_import_starts_after_two_quiet_polls(env: Env) -> None:
    watcher = poller(env)
    assert watcher.poll() is False
    put(env.inbox / "a.nes", 5)
    quiet(watcher)
    assert env.services.jobs.history() == []
    assert watcher.poll() is True
    env.services.jobs.wait(5)
    assert [(record.kind, record.ok) for record in env.services.jobs.history()] == [
        ("import", True)
    ]


def test_a_stall_of_one_interval_does_not_start_an_import(env: Env) -> None:
    watcher = poller(env)
    put(env.inbox / "a.nes", 5)
    assert [watcher.poll(), watcher.poll()] == [False, False]
    put(env.inbox / "a.nes", 9)
    quiet(watcher)
    assert watcher.poll() is True
    env.services.jobs.wait(5)


def test_a_same_size_replacement_counts_as_a_change(env: Env) -> None:
    watcher = poller(env)
    target = env.inbox / "a.nes"
    put(target, 3)
    assert [watcher.poll(), watcher.poll()] == [False, False]
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))
    assert [watcher.poll(), watcher.poll()] == [False, False]
    assert watcher.poll() is True
    env.services.jobs.wait(5)


def test_an_unchanged_file_set_is_not_retried(env: Env) -> None:
    watcher = poller(env)
    put(env.inbox / "a.nes")
    quiet(watcher)
    assert watcher.poll() is True
    env.services.jobs.wait(5)
    assert [watcher.poll(), watcher.poll(), watcher.poll()] == [False, False, False]
    put(env.inbox / "b.nes")
    quiet(watcher)
    assert watcher.poll() is True
    env.services.jobs.wait(5)
    assert len(env.services.jobs.history()) == 2


def test_files_left_behind_by_an_import_do_not_start_another(env: Env) -> None:
    def report(
        dat_files: object, inputs: list[Path], cache: object, excludes: object = ()
    ) -> list[igir.ReportRow]:
        return [igir.ReportRow("d", "FOUND", "g", str(env.inbox / "a.nes"))] * (
            1 if (env.inbox / "a.nes").exists() else 0
        )

    def move(*args: object) -> None:
        (env.inbox / "a.nes").unlink()

    tools = dataclasses.replace(env.services.tools, igir_report=report, igir_move=move)
    watcher = watch.Watcher(dataclasses.replace(env.services, tools=tools))
    put(env.inbox / "a.nes")
    put(env.inbox / "b.nes")
    quiet(watcher)
    assert watcher.poll() is True
    env.services.jobs.wait(5)
    assert [watcher.poll() for _ in range(4)] == [False] * 4
    assert len(env.services.jobs.history()) == 1
    put(env.inbox / "c.nes")
    quiet(watcher)
    assert watcher.poll() is True
    env.services.jobs.wait(5)


def test_the_same_file_returning_after_an_empty_inbox_is_imported_again(env: Env) -> None:
    watcher = poller(env)
    put(env.inbox / "a.nes")
    quiet(watcher)
    assert watcher.poll() is True
    env.services.jobs.wait(5)
    (env.inbox / "a.nes").unlink()
    assert watcher.poll() is False
    put(env.inbox / "a.nes")
    quiet(watcher)
    assert watcher.poll() is True
    env.services.jobs.wait(5)


def test_nothing_starts_while_a_job_runs(env: Env) -> None:
    release = threading.Event()
    env.services.jobs.start("scan", lambda: release.wait(5))
    watcher = poller(env)
    put(env.inbox / "a.nes")
    quiet(watcher)
    assert watcher.poll() is False
    release.set()
    env.services.jobs.wait(5)
    assert watcher.poll() is True
    env.services.jobs.wait(5)


def test_a_start_that_loses_the_race_is_refused_and_not_counted_as_an_attempt(
    env: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    release = threading.Event()
    env.services.jobs.start("scan", lambda: release.wait(5))
    monkeypatch.setattr(env.services.jobs, "current", lambda: None)
    watcher = poller(env)
    put(env.inbox / "a.nes")
    quiet(watcher)
    assert watcher.poll() is False
    assert capsys.readouterr().err == ""
    release.set()
    env.services.jobs.wait(5)
    assert watcher.poll() is True
    env.services.jobs.wait(5)


def test_a_failing_import_is_logged_and_not_repeated(env: Env) -> None:
    def broken(*args: object, **kwargs: object) -> list[igir.ReportRow]:
        raise OSError("disk gone")

    tools = dataclasses.replace(env.services.tools, igir_report=broken)
    watcher = watch.Watcher(dataclasses.replace(env.services, tools=tools))
    put(env.inbox / "a.nes")
    quiet(watcher)
    assert watcher.poll() is True
    env.services.jobs.wait(5)
    record = env.services.jobs.history()[0]
    assert not record.ok
    assert "disk gone" in record.output
    assert [watcher.poll() for _ in range(4)] == [False] * 4
    assert len(env.services.jobs.history()) == 1


def test_a_recurring_context_error_is_reported_each_time_it_returns(
    env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    failing = True
    context = env.context

    def factory() -> Context:
        if failing:
            raise ConfigError("library offline")
        return context

    watcher = watch.Watcher(dataclasses.replace(env.services, context_factory=factory))
    quiet(watcher)
    assert capsys.readouterr().err == "romledger: auto-import: library offline\n"
    failing = False
    put(env.inbox / "a.nes")
    quiet(watcher)
    assert watcher.poll() is True
    env.services.jobs.wait(5)
    failing = True
    quiet(watcher)
    assert capsys.readouterr().err == "romledger: auto-import: library offline\n"


def test_a_refused_start_is_reported_and_not_retried_for_the_same_files(
    env: Env, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def refuse(*args: object) -> None:
        calls.append(1)
        raise HTTPException(400, "no DAT")

    monkeypatch.setattr(actions, "start_import", refuse)
    watcher = poller(env)
    put(env.inbox / "a.nes")
    quiet(watcher)
    assert [watcher.poll() for _ in range(4)] == [False] * 4
    assert len(calls) == 1
    assert capsys.readouterr().err == "romledger: auto-import: no DAT\n"


def test_the_loop_sleeps_between_polls_and_survives_errors(
    env: Env, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    watcher = watch.Watcher(env.services, 2.5)
    sleeps: list[float] = []
    polls: list[int] = []

    def poll() -> bool:
        polls.append(1)
        if len(polls) == 1:
            raise RuntimeError("boom")
        return False

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(watcher, "poll", poll)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(watcher.run(sleep))
    assert sleeps == [2.5, 2.5, 2.5]
    assert len(polls) == 2
    assert "RuntimeError: boom" in capsys.readouterr().err


def test_running_cancels_the_loop_on_exit(env: Env) -> None:
    stopped: list[bool] = []

    class Loop:
        async def run(self) -> None:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                stopped.append(True)
                raise

    async def scenario() -> None:
        async with watch.running(Loop()):  # type: ignore[arg-type]
            await asyncio.sleep(0)

    asyncio.run(scenario())
    assert stopped == [True]


def test_pages_say_when_auto_import_is_on(env: Env) -> None:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    app_off = web_app.create_app(lambda: env.context, TOKEN)
    with TestClient(app_off, headers=headers) as client:
        assert "automatically" not in client.get("/inbox").text
    app = web_app.create_app(lambda: env.context, TOKEN, auto_import=True, poll_seconds=3600)
    with TestClient(app, headers=headers) as client:
        assert "imported into the library automatically" in client.get("/inbox").text
        assert "automatic imports" in client.get("/activity").text
    assert "automatic imports" not in env.client.get("/activity").text
