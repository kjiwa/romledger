import pytest
from fastapi.testclient import TestClient

from romledger.web import views

from .support import TOKEN, Env


@pytest.fixture
def failing(env: Env, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    def explode(*args: object) -> None:
        raise RuntimeError(f"secret {TOKEN}")

    monkeypatch.setattr(views, "list_inbox", explode)
    monkeypatch.setattr(views, "platform_views", explode)
    return TestClient(env.client.app, headers=env.bearer(), raise_server_exceptions=False)


def test_unexpected_errors_render_the_error_page(failing: TestClient) -> None:
    response = failing.get("/inbox")
    assert response.status_code == 500
    assert "Something went wrong" in response.text
    assert TOKEN not in response.text
    assert response.headers["Content-Security-Policy"]


def test_unexpected_api_errors_are_json(failing: TestClient) -> None:
    response = failing.get("/api/platforms")
    assert response.status_code == 500
    assert list(response.json()) == ["error"]
    assert TOKEN not in response.text
