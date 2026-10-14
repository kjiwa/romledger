import io
import sys
import threading
import traceback
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TextIO, cast

from romledger import dats, igir
from romledger.config import ConfigError

HISTORY_SIZE = 50
EXPECTED_ERRORS = (ConfigError, dats.DatError, igir.ToolError, OSError)

Work = Callable[[], bool]
Clock = Callable[[], datetime]


class JobBusy(Exception):
    def __init__(self, kind: str) -> None:
        super().__init__(f"a {kind} is already running. Wait for it to finish.")


@dataclass(frozen=True)
class Running:
    id: int
    kind: str
    started: str


@dataclass(frozen=True)
class Record:
    id: int
    kind: str
    ok: bool
    started: str
    finished: str
    output: str


def now() -> datetime:
    return datetime.now(UTC)


class _ThreadStream:
    def __init__(self, original: TextIO, buffer: io.StringIO, owner: int) -> None:
        self._original = original
        self._buffer = buffer
        self._owner = owner

    def write(self, text: str) -> int:
        target = self._buffer if threading.get_ident() == self._owner else self._original
        return target.write(text)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original, name)


@contextmanager
def _captured(buffer: io.StringIO) -> Iterator[None]:
    owner = threading.get_ident()
    original = sys.stdout, sys.stderr
    sys.stdout = cast(TextIO, _ThreadStream(original[0], buffer, owner))
    sys.stderr = cast(TextIO, _ThreadStream(original[1], buffer, owner))
    try:
        yield
    finally:
        sys.stdout, sys.stderr = original


class Jobs:
    def __init__(self, clock: Clock = now) -> None:
        self._clock = clock
        self._state = threading.Lock()
        self._running: Running | None = None
        self._history: deque[Record] = deque(maxlen=HISTORY_SIZE)
        self._thread: threading.Thread | None = None
        self._counter = 0

    def start(self, kind: str, work: Work) -> Running:
        with self._state:
            if self._running is not None:
                raise JobBusy(self._running.kind)
            job = Running(self._counter + 1, kind, self._clock().isoformat())
            thread = threading.Thread(target=self._run, args=(job, work), daemon=True)
            self._running = job
            try:
                thread.start()
            except BaseException:
                self._running = None
                raise
            self._counter = job.id
            self._thread = thread
        return job

    def current(self) -> Running | None:
        with self._state:
            return self._running

    def history(self) -> list[Record]:
        with self._state:
            return list(reversed(self._history))

    def wait(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self, job: Running, work: Work) -> None:
        try:
            buffer = io.StringIO()
            with _captured(buffer):
                ok = _call(work)
            record = Record(
                job.id, job.kind, ok, job.started, self._clock().isoformat(), buffer.getvalue()
            )
            with self._state:
                self._history.append(record)
        finally:
            with self._state:
                self._running = None


def _call(work: Work) -> bool:
    try:
        return work()
    except EXPECTED_ERRORS as error:
        print(f"romledger: error: {error}")
    except Exception:
        print(traceback.format_exc())
    return False
