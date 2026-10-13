from collections.abc import Callable
from pathlib import Path

import pytest

from romledger import http

FakeThrottle = Callable[[float], tuple[http.Throttle, list[float]]]


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
