from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import httpx
import pytest

from romledger import http, scan, term

FakeThrottle = Callable[[float], tuple[http.Throttle, list[float]]]


class Serving(Protocol):
    def __call__(
        self, content: dict[str, str], requested: list[str] | None = None
    ) -> scan.ClientFactory: ...


@pytest.fixture
def fixtures() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def fake_throttle() -> FakeThrottle:
    def build(gap: float) -> tuple[http.Throttle, list[float]]:
        now = [0.0]
        sleeps: list[float] = []

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            now[0] += seconds

        return http.Throttle(gap, clock=lambda: now[0], sleep=sleep), sleeps

    return build


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"test tried to reach {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


@pytest.fixture
def stderr_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(term, "stderr_is_tty", lambda: True)


@pytest.fixture
def serving() -> Serving:
    def build(content: dict[str, str], requested: list[str] | None = None) -> scan.ClientFactory:
        def handler(request: httpx.Request) -> httpx.Response:
            name = request.url.path.rsplit("/", 1)[-1]
            if requested is not None:
                requested.append(name)
            text = content.get(name)
            return httpx.Response(200, text=text) if text else httpx.Response(404)

        return lambda proxy: httpx.Client(transport=httpx.MockTransport(handler))

    return build
