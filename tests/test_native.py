import io
import json
import os
import struct
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from romledger import __version__, config, importer, native, registry, state
from romledger.context import Context

LENGTH = struct.Struct("=I")


def frame(message: object) -> bytes:
    payload = json.dumps(message).encode()
    return LENGTH.pack(len(payload)) + payload


def unframe(data: bytes) -> list[dict[str, Any]]:
    stream = io.BytesIO(data)
    found = []
    while (message := native.read_message(stream)) is not None:
        found.append(message)
    return found


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.roms, self.inbox = tmp_path / "roms", tmp_path / "inbox"
        self.roms.mkdir()
        self.inbox.mkdir()
        entries = registry.load()
        cfg = config.Config(
            config.Library(self.roms, (self.inbox,)),
            {slug: config.Platform(entries[slug].dat) for slug in ("nes", "snes")},
        )
        self.context = Context(tmp_path / "config.toml", cfg, entries, tmp_path / "data")
        self.imports = 0
        self.import_result = importer.ImportResult({"nes": 1}, [], [], [], [])
        self.host = native.Host(lambda: self.context, self.run_import)

    def run_import(self, context: Context) -> importer.ImportResult:
        self.imports += 1
        return self.import_result

    def seed(self) -> None:
        items = [state.Item("Alpha (USA)", "have", "/a"), state.Item("Beta (USA)", "missing", None)]
        with state.State(self.context.data_dir / "state.db") as database:
            database.replace_platform("nes", items, [], "1", "2026-10-13T12:00:00+00:00")


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_a_message_round_trips() -> None:
    stream = io.BytesIO()
    native.write_message(stream, {"id": 1, "text": "héllo"})
    assert unframe(stream.getvalue()) == [{"id": 1, "text": "héllo"}]


def test_the_end_of_input_is_not_an_error() -> None:
    assert native.read_message(io.BytesIO(b"")) is None


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"\x01\x00", "length was cut short"),
        (LENGTH.pack(native.MAX_MESSAGE + 1), "over the"),
        (LENGTH.pack(10) + b"{}", "message was cut short"),
        (LENGTH.pack(3) + b"{{{", "not JSON"),
        (frame([1, 2]), "not a JSON object"),
    ],
)
def test_bad_framing_is_a_protocol_error(data: bytes, message: str) -> None:
    with pytest.raises(native.ProtocolError, match=message):
        native.read_message(io.BytesIO(data))


def test_ping_reports_the_version(env: Env) -> None:
    assert native.reply(env.host, {"id": 4, "type": "ping"}) == {
        "id": 4,
        "ok": True,
        "data": {"version": __version__},
    }


def test_platforms_lists_every_platform_with_its_counts(env: Env) -> None:
    env.seed()
    answer = native.reply(env.host, {"id": 1, "type": "platforms"})
    rows = {row["slug"]: row for row in answer["data"]}
    assert answer["ok"] is True
    assert rows["nes"]["tracked"] is True
    assert rows["nes"]["percent"] == 50
    assert rows["snes"]["tracked"] is False


def test_lookup_by_hash(env: Env) -> None:
    answer = native.reply(env.host, {"id": 1, "type": "lookup", "sha1": "AB" * 20})
    assert answer["data"]["matches"] == [
        {"platform": None, "game": None, "state": "unknown", "exact": True}
    ]


def test_lookup_by_name(env: Env) -> None:
    env.seed()
    request = {"id": 1, "type": "lookup", "name": "Alpha (USA)", "platform": "nes", "regions": []}
    answer = native.reply(env.host, request)
    assert answer["data"]["matches"][0]["platform"] == "nes"


def test_lookup_by_name_passes_regions_and_skips_empty_ones(env: Env) -> None:
    env.seed()
    request = {"type": "lookup", "name": "Alpha", "platform": "nes", "regions": ["USA", "", None]}
    assert native.reply(env.host, request)["ok"] is True


def test_lookup_rejects_an_unknown_platform(env: Env) -> None:
    request = {"id": 1, "type": "lookup", "name": "A", "platform": "zzz"}
    assert native.reply(env.host, request) == {
        "id": 1,
        "ok": False,
        "error": "unknown platform 'zzz'",
    }


@pytest.mark.parametrize(
    "request_body",
    [
        {"type": "lookup"},
        {"type": "lookup", "name": "A"},
        {"type": "lookup", "sha1": "a", "name": "b"},
    ],
)
def test_lookup_needs_a_hash_or_a_name_and_a_platform(
    env: Env, request_body: dict[str, Any]
) -> None:
    answer = native.reply(env.host, request_body)
    assert answer["ok"] is False
    assert "needs a sha1, or a name and a platform" in answer["error"]


def test_an_unknown_request_is_refused(env: Env) -> None:
    answer = native.reply(env.host, {"id": 9, "type": "format-disk"})
    assert answer == {"id": 9, "ok": False, "error": "unknown request 'format-disk'"}


def test_import_runs_for_a_file_in_an_inbox(env: Env) -> None:
    path = str(env.inbox / "Game (USA).zip")
    answer = native.reply(env.host, {"id": 1, "type": "import", "path": path})
    assert answer == {"id": 1, "ok": True, "data": {"lines": ["moved nes 1"], "failures": []}}
    assert env.imports == 1


def test_import_reports_hook_failures(env: Env) -> None:
    env.import_result = importer.ImportResult({"nes": 1}, [], [], [], ["touch x: exit status 1"])
    answer = native.reply(env.host, {"type": "import", "path": str(env.inbox / "a.zip")})
    assert answer["data"]["failures"] == ["touch x: exit status 1"]


@pytest.mark.parametrize("path", [None, 5, "relative/a.zip"])
def test_import_needs_an_absolute_path(env: Env, path: object) -> None:
    answer = native.reply(env.host, {"type": "import", "path": path})
    assert answer["ok"] is False
    assert "absolute path" in answer["error"]
    assert env.imports == 0


def test_import_refuses_a_file_outside_every_inbox(env: Env, tmp_path: Path) -> None:
    answer = native.reply(env.host, {"type": "import", "path": str(tmp_path / "x" / "a.zip")})
    assert answer["ok"] is False
    assert f"{tmp_path / 'x'} is not an inbox. Add it to library.inboxes in " in answer["error"]
    assert env.imports == 0


def test_import_does_not_follow_a_symlink_out_of_the_inbox(env: Env, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (env.inbox / "link").symlink_to(outside)
    answer = native.reply(env.host, {"type": "import", "path": str(env.inbox / "link" / "a.zip")})
    assert answer["ok"] is False
    assert env.imports == 0


def test_expected_errors_become_error_replies(env: Env) -> None:
    def failing(context: Context) -> importer.ImportResult:
        raise config.ConfigError("no DAT could be downloaded (1 failed). boom")

    host = native.Host(lambda: env.context, failing)
    answer = native.reply(host, {"id": 3, "type": "import", "path": str(env.inbox / "a.zip")})
    assert answer == {
        "id": 3,
        "ok": False,
        "error": "no DAT could be downloaded (1 failed). boom",
    }


def test_a_config_that_cannot_load_is_an_error_reply() -> None:
    def broken() -> Context:
        raise config.ConfigError("roms: not a directory")

    answer = native.reply(native.Host(broken), {"id": 2, "type": "platforms"})
    assert answer == {"id": 2, "ok": False, "error": "roms: not a directory"}


def test_an_unexpected_error_is_logged_and_hidden(
    env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(context: Context) -> importer.ImportResult:
        raise RuntimeError("secret detail")

    host = native.Host(lambda: env.context, explode)
    answer = native.reply(host, {"type": "import", "path": str(env.inbox / "a.zip")})
    assert answer == {"id": None, "ok": False, "error": "romledger hit an unexpected error"}
    assert "secret detail" in capsys.readouterr().err


def test_serve_answers_each_request_with_its_id(env: Env) -> None:
    env.seed()
    requests = b"".join(
        frame({"id": number, "type": kind})
        for number, kind in ((1, "ping"), (2, "platforms"), (3, "bogus"))
    )
    out = io.BytesIO()
    native.serve(io.BytesIO(requests), out, env.host)
    answers = {answer["id"]: answer for answer in unframe(out.getvalue())}
    assert [answers[n]["ok"] for n in (1, 2, 3)] == [True, True, False]


def test_serve_stops_on_a_protocol_error(env: Env) -> None:
    with pytest.raises(native.ProtocolError):
        native.serve(io.BytesIO(b"\x01"), io.BytesIO(), env.host)


def test_imports_that_arrive_together_share_runs() -> None:
    entered, release = threading.Event(), threading.Event()
    runs: list[int] = []

    def job() -> int:
        runs.append(len(runs) + 1)
        entered.set()
        release.wait(5)
        return runs[-1]

    coalescer = native.Coalescer(job)
    answers: list[int] = []
    threads = [
        threading.Thread(target=lambda: answers.append(coalescer.request())) for _ in range(6)
    ]
    threads[0].start()
    assert entered.wait(5)
    for thread in threads[1:]:
        thread.start()
    release.set()
    for thread in threads:
        thread.join(5)
    assert sorted(answers) == [1, 2, 2, 2, 2, 2]
    assert runs == [1, 2]


def test_a_failed_run_fails_every_request_that_shared_it() -> None:
    entered, release = threading.Event(), threading.Event()

    def job() -> None:
        entered.set()
        release.wait(5)
        raise config.ConfigError("boom")

    coalescer = native.Coalescer(job)
    errors: list[str] = []

    def call() -> None:
        try:
            coalescer.request()
        except config.ConfigError as error:
            errors.append(str(error))

    first = threading.Thread(target=call)
    first.start()
    assert entered.wait(5)
    second = threading.Thread(target=call)
    second.start()
    release.set()
    first.join(5)
    second.join(5)
    assert errors == ["boom", "boom"]


def test_old_outcomes_are_dropped() -> None:
    coalescer = native.Coalescer(lambda: "ok")
    for _ in range(native.OUTCOMES_KEPT + 4):
        assert coalescer.request() == "ok"
    assert len(coalescer._outcomes) <= native.OUTCOMES_KEPT


def test_the_launcher_style_process_speaks_the_protocol(tmp_path: Path) -> None:
    roms, inbox = tmp_path / "roms", tmp_path / "inbox"
    roms.mkdir()
    inbox.mkdir()
    config_file = tmp_path / "config.toml"
    config_file.write_text(f'[library]\nroms = "{roms}"\ninboxes = ["{inbox}"]\n')
    env = {**os.environ, config.CONFIG_ENV: str(config_file), config.DATA_ENV: str(tmp_path / "d")}
    done = subprocess.run(
        [sys.executable, "-m", "romledger.native"],
        input=frame({"id": 1, "type": "ping"}) + frame({"id": 2, "type": "platforms"}),
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )
    answers = {answer["id"]: answer for answer in unframe(done.stdout)}
    assert done.returncode == 0, done.stderr
    assert answers[1]["ok"] is True
    assert len(answers[2]["data"]) == len(registry.load())


def test_main_reports_a_broken_stream(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class Stdin:
        buffer = io.BytesIO(b"\x01")

    monkeypatch.setattr(sys, "stdin", Stdin())
    monkeypatch.setattr(os, "dup2", lambda *args: None)
    monkeypatch.setattr(os, "dup", lambda fd: os.open(os.devnull, os.O_WRONLY))
    assert native.main() == 1


def test_main_returns_zero_when_the_browser_closes_the_pipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Stdin:
        buffer = io.BytesIO(b"")

    monkeypatch.setattr(sys, "stdin", Stdin())
    monkeypatch.setattr(os, "dup2", lambda *args: None)
    monkeypatch.setattr(os, "dup", lambda fd: os.open(os.devnull, os.O_WRONLY))
    assert native.main() == 0


def test_the_module_runs_as_a_script(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    (tmp_path / "roms").mkdir()
    (tmp_path / "inbox").mkdir()
    config_file.write_text(
        f'[library]\nroms = "{tmp_path / "roms"}"\ninboxes = ["{tmp_path / "inbox"}"]\n'
    )
    env = {**os.environ, config.CONFIG_ENV: str(config_file)}
    done = subprocess.run(
        [sys.executable, "-m", "romledger.native"],
        input=b"\x07",
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert done.returncode == 1
    assert done.stdout == b""
    assert b"native host: the message length was cut short" in done.stderr


def test_the_default_import_runs_locked_against_the_loaded_config(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[config.Config, Path]] = []

    def locked(cfg: config.Config, data: Path) -> importer.ImportResult:
        seen.append((cfg, data))
        return importer.ImportResult({"snes": 2}, [], [], [], [])

    monkeypatch.setattr(importer, "import_locked", locked)
    host = native.Host(lambda: env.context)
    answer = native.reply(host, {"type": "import", "path": str(env.inbox / "a.zip")})
    assert answer["data"]["lines"] == ["moved snes 2"]
    assert seen == [(env.context.config, env.context.data_dir)]


def test_the_extension_connects_to_the_host_the_installer_registers() -> None:
    background = (Path(__file__).parent.parent / "extension" / "background.js").read_text()
    assert f'const HOST = "{native.HOST_NAME}";' in background
