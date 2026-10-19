import threading
from pathlib import Path

from romledger import lock


def test_the_lock_is_free_when_nobody_holds_it(tmp_path: Path) -> None:
    waited: list[bool] = []
    with lock.exclusive(tmp_path / "data" / "import.lock", lambda: waited.append(True)):
        pass
    assert waited == []
    assert (tmp_path / "data" / "import.lock").is_file()


def test_a_second_holder_waits_until_the_first_lets_go(tmp_path: Path) -> None:
    path = tmp_path / "import.lock"
    events: list[str] = []
    waiting = threading.Event()

    def wait() -> None:
        events.append("waiting")
        waiting.set()

    def second() -> None:
        with lock.exclusive(path, wait):
            events.append("second")

    with lock.exclusive(path):
        thread = threading.Thread(target=second)
        thread.start()
        assert waiting.wait(5)
        events.append("first done")
    thread.join(5)
    assert events == ["waiting", "first done", "second"]
