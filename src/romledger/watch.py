import fnmatch
import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from romledger import igir
from romledger.config import ConfigError
from romledger.context import Context
from romledger.igir import ToolError

POLL_SECONDS = 5.0
STEADY_POLLS = 2
JUNK_PATTERNS = tuple(pattern.rsplit("/", 1)[-1] for pattern in igir.JUNK_EXCLUDES)
EXPECTED_ERRORS = (ConfigError, ToolError, OSError)

Snapshot = dict[str, tuple[int, int]]


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
    def __init__(
        self,
        load: Callable[[], Context],
        run_import: Callable[[Context], object],
        warn: Callable[[str], None],
        interval: float = POLL_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._load = load
        self._run_import = run_import
        self._warn = warn
        self._interval = interval
        self._sleep = sleep
        self._previous: Snapshot = {}
        self._attempted: Snapshot = {}
        self._steady = 0
        self._warned = ""

    def poll(self) -> bool:
        try:
            context = self._load()
        except EXPECTED_ERRORS as error:
            self._complain(str(error))
            return False
        self._warned = ""
        current = snapshot(context.config.library.inboxes)
        self._steady = self._steady + 1 if current == self._previous else 0
        self._previous = current
        if not current:
            self._attempted = {}
        if self._steady < STEADY_POLLS or not current or current == self._attempted:
            return False
        self._attempted = current
        try:
            self._run_import(context)
        except EXPECTED_ERRORS as error:
            self._complain(str(error))
            return False
        after = snapshot(context.config.library.inboxes)
        self._attempted = {
            path: stamp for path, stamp in after.items() if current.get(path) == stamp
        }
        return True

    def run(self) -> None:
        while True:
            self._sleep(self._interval)
            self.poll()

    def _complain(self, message: str) -> None:
        if message != self._warned:
            self._warned = message
            self._warn(message)
