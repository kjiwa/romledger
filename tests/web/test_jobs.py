import sys
import threading
from datetime import UTC, datetime, timedelta

import pytest

from romledger import dats
from romledger.config import ConfigError
from romledger.web import jobs, views


def test_history_records_output_newest_first() -> None:
    queue = jobs.Jobs()

    def work() -> bool:
        print("hello")
        return True

    queue.start("scan", work)
    queue.wait(5)
    queue.start("import", lambda: False)
    queue.wait(5)
    first, second = queue.history()[1], queue.history()[0]
    assert (first.kind, first.ok, first.output) == ("scan", True, "hello\n")
    assert (second.kind, second.ok) == ("import", False)
    assert (first.id, second.id) == (1, 2)
    assert queue.current() is None


@pytest.mark.parametrize("error", [ConfigError("c"), dats.DatError("d"), OSError("o")])
def test_expected_errors_print_a_message_without_a_traceback(error: Exception) -> None:
    queue = jobs.Jobs()

    def work() -> bool:
        raise error

    queue.start("scan", work)
    queue.wait(5)
    record = queue.history()[0]
    assert not record.ok
    assert record.output.startswith("romledger: error: ")
    assert "Traceback" not in record.output


def test_unexpected_errors_keep_the_traceback_and_release_the_lock() -> None:
    queue = jobs.Jobs()

    def work() -> bool:
        raise RuntimeError("boom")

    queue.start("scan", work)
    queue.wait(5)
    assert "RuntimeError: boom" in queue.history()[0].output
    queue.start("scan", lambda: True)
    queue.wait(5)
    assert len(queue.history()) == 2


def test_one_job_at_a_time() -> None:
    queue = jobs.Jobs()
    release = threading.Event()
    queue.start("scan", lambda: release.wait(5))
    with pytest.raises(jobs.JobBusy, match="scan is already running"):
        queue.start("import", lambda: True)
    release.set()
    queue.wait(5)


def test_history_is_bounded() -> None:
    queue = jobs.Jobs()
    for _ in range(jobs.HISTORY_SIZE + 3):
        queue.start("scan", lambda: True)
        queue.wait(5)
    assert len(queue.history()) == jobs.HISTORY_SIZE


def test_wait_without_a_job_returns() -> None:
    jobs.Jobs().wait(0.01)


def test_duration_and_stamp() -> None:
    start = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
    assert views.duration(start.isoformat(), (start + timedelta(seconds=7)).isoformat()) == "7 s"
    assert (
        views.duration(start.isoformat(), (start + timedelta(seconds=135)).isoformat())
        == "2 min 15 s"
    )
    assert views.stamp(start.isoformat()) == "2026-10-13 12:00 UTC"


def test_human_size() -> None:
    assert views.human_size(5) == "5 B"
    assert views.human_size(2048) == "2.0 KB"
    assert views.human_size(3 * 1024**2) == "3.0 MB"
    assert views.human_size(5 * 1024**3) == "5.0 GB"


def test_page_url_drops_empty_params() -> None:
    assert views.page_url("/p", {"q": "", "state": "all"}, 20) == "/p?state=all&offset=20"


def test_output_capture_ignores_other_threads(capsys: pytest.CaptureFixture[str]) -> None:
    queue = jobs.Jobs()
    printed, release = threading.Event(), threading.Event()

    def work() -> bool:
        print("from job")
        printed.set()
        release.wait(5)
        return True

    queue.start("scan", work)
    printed.wait(5)
    print("from elsewhere")
    release.set()
    queue.wait(5)
    assert queue.history()[0].output == "from job\n"
    assert "from elsewhere" in capsys.readouterr().out


def test_streams_are_restored_after_a_job() -> None:
    before = sys.stdout, sys.stderr
    queue = jobs.Jobs()
    queue.start("scan", lambda: True)
    queue.wait(5)
    assert (sys.stdout, sys.stderr) == before


def test_thread_start_failure_releases_the_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    queue = jobs.Jobs()
    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", _refuse_to_start)
        with pytest.raises(RuntimeError, match="no threads"):
            queue.start("scan", lambda: True)
    assert queue.current() is None
    queue.start("scan", lambda: True)
    queue.wait(5)
    assert queue.history()[0].ok


def _refuse_to_start(self: threading.Thread) -> None:
    raise RuntimeError("no threads")


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_failure_building_the_record_releases_the_slot() -> None:
    calls = iter([datetime(2026, 10, 13, tzinfo=UTC)])

    def clock() -> datetime:
        try:
            return next(calls)
        except StopIteration:
            raise RuntimeError("clock") from None

    queue = jobs.Jobs(clock)
    queue.start("scan", lambda: True)
    queue.wait(5)
    assert queue.current() is None
    assert queue.history() == []


def test_captured_streams_delegate_other_attributes() -> None:
    seen: list[object] = []

    def work() -> bool:
        seen.append(sys.stdout.isatty())
        return True

    queue = jobs.Jobs()
    queue.start("scan", work)
    queue.wait(5)
    assert seen in ([True], [False])
