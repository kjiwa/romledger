import dataclasses
import json
import os
import struct
import sys
import threading
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, BinaryIO

from romledger import __version__, dats, importer, lookup, overview, state
from romledger.config import ConfigError
from romledger.context import Context, load_context
from romledger.igir import ToolError

HOST_NAME = "io.github.kjiwa.romledger"
MAX_MESSAGE = 1 << 20
LENGTH = struct.Struct("=I")
WORKERS = 4
OUTCOMES_KEPT = 16
EXPECTED_ERRORS = (ConfigError, dats.DatError, ToolError, OSError)

Request = dict[str, Any]
Handler = Callable[[Context, Request], Any]


class ProtocolError(Exception):
    pass


class HostError(Exception):
    pass


def read_message(stream: BinaryIO) -> Request | None:
    header = stream.read(LENGTH.size)
    if not header:
        return None
    if len(header) < LENGTH.size:
        raise ProtocolError("the message length was cut short")
    (size,) = LENGTH.unpack(header)
    if size > MAX_MESSAGE:
        raise ProtocolError(f"a message of {size} bytes is over the {MAX_MESSAGE} byte limit")
    payload = stream.read(size)
    if len(payload) < size:
        raise ProtocolError("the message was cut short")
    try:
        message = json.loads(payload)
    except ValueError as error:
        raise ProtocolError(f"the message is not JSON: {error}") from error
    if not isinstance(message, dict):
        raise ProtocolError("the message is not a JSON object")
    return message


def write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    payload = json.dumps(message, separators=(",", ":")).encode()
    stream.write(LENGTH.pack(len(payload)) + payload)
    stream.flush()


# Runs one job at a time. Requests that arrive while it runs share the next run, so ten downloads
# that finish together cause two imports, not ten.
class Coalescer:
    def __init__(self, job: Callable[[], Any]) -> None:
        self._job = job
        self._cond = threading.Condition()
        self._started = 0
        self._finished = 0
        self._outcomes: dict[int, tuple[Any, BaseException | None]] = {}

    def request(self) -> Any:
        with self._cond:
            target = self._started + 1
            while self._finished < target and (self._running() or self._started + 1 != target):
                self._cond.wait()
            if self._finished >= target:
                return self._answer(target)
            self._started = target
        result: Any = None
        failure: BaseException | None = None
        try:
            result = self._job()
        except BaseException as error:
            failure = error
        with self._cond:
            self._outcomes[target] = (result, failure)
            self._outcomes.pop(target - OUTCOMES_KEPT, None)
            self._finished = target
            self._cond.notify_all()
            return self._answer(target)

    def _running(self) -> bool:
        return self._started > self._finished

    def _answer(self, target: int) -> Any:
        result, failure = self._outcomes[target]
        if failure is not None:
            raise failure
        return result


class Host:
    def __init__(
        self,
        load: Callable[[], Context] = lambda: load_context(None),
        run_import: Callable[[Context], importer.ImportResult] | None = None,
    ) -> None:
        self._load = load
        self._run_import = run_import or _import
        self._imports = Coalescer(lambda: self._run_import(self._load()))
        self._handlers: dict[str, Handler] = {
            "ping": lambda context, request: {"version": __version__},
            "platforms": self._platforms,
            "lookup": self._lookup,
            "import": self._import,
        }

    def handle(self, request: Request) -> Any:
        handler = self._handlers.get(str(request.get("type")))
        if handler is None:
            raise HostError(f"unknown request {request.get('type')!r}")
        return handler(self._load(), request)

    def _platforms(self, context: Context, request: Request) -> Any:
        with state.State(context.data_dir / "state.db") as database:
            return overview.platform_rows(context, database)

    def _lookup(self, context: Context, request: Request) -> Any:
        sha1, name = request.get("sha1"), request.get("name")
        with state.State(context.data_dir / "state.db") as database:
            if isinstance(sha1, str) and name is None:
                matches = lookup.by_hash(database, sha1)
            elif isinstance(name, str) and isinstance(request.get("platform"), str):
                platform = request["platform"]
                if platform not in context.config.platforms:
                    raise HostError(f"unknown platform {platform!r}")
                regions = [str(region) for region in request.get("regions") or [] if region]
                matches = lookup.by_name(database, platform, name, regions)
            else:
                raise HostError("a lookup needs a sha1, or a name and a platform")
        return {"matches": [dataclasses.asdict(match) for match in matches]}

    def _import(self, context: Context, request: Request) -> Any:
        _check_inbox_path(context, request.get("path"))
        result = self._imports.request()
        return {
            "lines": importer.import_lines(result, dry_run=False),
            "failures": result.hook_failures,
        }


def _import(context: Context) -> importer.ImportResult:
    return importer.import_locked(context.config, context.data_dir)


def _check_inbox_path(context: Context, raw: object) -> None:
    if not isinstance(raw, str) or not os.path.isabs(raw):
        raise HostError("an import needs the absolute path of the downloaded file")
    path = Path(raw).resolve()
    inboxes = [inbox.resolve() for inbox in context.config.library.inboxes]
    if not any(path.is_relative_to(inbox) for inbox in inboxes):
        raise HostError(
            f"{path.parent} is not an inbox. Add it to library.inboxes in {context.path}."
        )


def reply(host: Host, request: Request) -> dict[str, Any]:
    identifier = request.get("id")
    try:
        return {"id": identifier, "ok": True, "data": host.handle(request)}
    except (HostError, *EXPECTED_ERRORS) as error:
        return {"id": identifier, "ok": False, "error": str(error)}
    except Exception:
        print(traceback.format_exc(), file=sys.stderr)
        return {"id": identifier, "ok": False, "error": "romledger hit an unexpected error"}


def serve(stdin: BinaryIO, stdout: BinaryIO, host: Host) -> None:
    lock = threading.Lock()

    def answer(request: Request) -> None:
        response = reply(host, request)
        with lock:
            write_message(stdout, response)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        while (request := read_message(stdin)) is not None:
            pool.submit(answer, request)


def main() -> int:
    with os.fdopen(os.dup(sys.stdout.fileno()), "wb") as protocol:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        try:
            serve(sys.stdin.buffer, protocol, Host())
        except ProtocolError as error:
            print(f"romledger: native host: {error}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
