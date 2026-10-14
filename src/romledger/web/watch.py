import asyncio
import fnmatch
import os
import sys
import traceback
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import HTTPException

from romledger import igir
from romledger.context import Context
from romledger.web import actions
from romledger.web.deps import Services
from romledger.web.jobs import EXPECTED_ERRORS

POLL_SECONDS = 5.0
HTTP_BUSY = 409
JUNK_PATTERNS = tuple(pattern.rsplit("/", 1)[-1] for pattern in igir.JUNK_EXCLUDES)

STEADY_POLLS = 2

Snapshot = dict[str, tuple[int, int]]
Sleep = Callable[[float], Awaitable[None]]


def snapshot(inboxes: Sequence[Path]) -> Snapshot:
    found: Snapshot = {}
    for inbox in inboxes:
        for directory, names, filenames in os.walk(inbox):
            if Path(directory) == inbox:
                names[:] = [name for name in names if name not in igir.SET_ASIDE]
            for filename in filenames:
                if any(fnmatch.fnmatchcase(filename, pattern) for pattern in JUNK_PATTERNS):
                    continue
                path = Path(directory) / filename
                try:
                    stat = path.stat()
                except OSError:
                    continue
                found[str(path)] = (stat.st_size, stat.st_mtime_ns)
    return found


class Watcher:
    def __init__(self, services: Services, interval: float = POLL_SECONDS) -> None:
        self._services = services
        self._interval = interval
        self._previous: Snapshot = {}
        self._attempted: Snapshot = {}
        self._started: Snapshot | None = None
        self._steady = 0
        self._warned = ""

    def poll(self) -> bool:
        try:
            context = self._services.context_factory()
        except EXPECTED_ERRORS as error:
            self._warn(str(error))
            return False
        self._warned = ""
        current = snapshot(context.config.library.inboxes)
        self._observe(current)
        if self._steady < STEADY_POLLS or not current or current == self._attempted:
            return False
        return self._start_import(context, current)

    def _observe(self, current: Snapshot) -> None:
        self._steady = self._steady + 1 if current == self._previous else 0
        self._previous = current
        if not current:
            self._attempted = {}
        if self._started is not None and self._services.jobs.current() is None:
            self._attempted = {
                path: stamp for path, stamp in current.items() if self._started.get(path) == stamp
            }
            self._started = None

    def _start_import(self, context: Context, current: Snapshot) -> bool:
        try:
            actions.start_import(context, self._services)
        except HTTPException as error:
            if error.status_code == HTTP_BUSY:
                return False
            self._attempted = current
            self._warn(str(error.detail))
            return False
        self._attempted = current
        self._started = current
        return True

    async def run(self, sleep: Sleep = asyncio.sleep) -> None:
        while True:
            await sleep(self._interval)
            try:
                await asyncio.to_thread(self.poll)
            except Exception:
                print(traceback.format_exc(), file=sys.stderr)

    def _warn(self, message: str) -> None:
        if message != self._warned:
            self._warned = message
            print(f"romledger: auto-import: {message}", file=sys.stderr)


@asynccontextmanager
async def running(watcher: Watcher) -> AsyncIterator[None]:
    task = asyncio.create_task(watcher.run())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
