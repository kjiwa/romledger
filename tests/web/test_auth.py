from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from romledger import config
from romledger.web import auth

from .support import TOKEN, Env


def anonymous(env: Env) -> TestClient:
    return TestClient(env.client.app)


def test_no_credentials_is_refused_with_a_hint(env: Env) -> None:
    page = anonymous(env).get("/")
    assert page.status_code == 401
    assert page.headers["www-authenticate"] == "Bearer"
    assert "romledger serve" in page.text
    assert "Sign in" in page.text
    api = anonymous(env).get("/api/platforms")
    assert api.status_code == 401
    assert "Authorization: Bearer" in api.json()["detail"]


def test_wrong_token_is_refused(env: Env) -> None:
    client = anonymous(env)
    assert client.get("/api/platforms", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/platforms", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get("/?token=nope").status_code == 401


def test_bearer_header_is_accepted(env: Env) -> None:
    assert anonymous(env).get("/api/platforms", headers=env.bearer()).status_code == 200


def test_token_link_sets_an_http_only_cookie_then_works(env: Env) -> None:
    client = anonymous(env)
    response = client.get(f"/?token={TOKEN}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{auth.COOKIE}={TOKEN}")
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Secure" not in cookie
    assert client.get("/").status_code == 200
    assert client.get("/api/platforms").status_code == 200


def test_cookie_is_secure_over_https(env: Env) -> None:
    client = TestClient(env.client.app, base_url="https://testserver")
    response = client.get(f"/?token={TOKEN}", follow_redirects=False)
    assert "Secure" in response.headers["set-cookie"]


def test_token_in_query_is_not_accepted_off_the_root_page(env: Env) -> None:
    assert anonymous(env).get(f"/api/platforms?token={TOKEN}").status_code == 401


def test_cross_origin_post_is_blocked(env: Env) -> None:
    response = env.client.post("/api/scan", headers={"Origin": "http://evil.example"})
    assert response.status_code == 403
    assert "Cross-origin" in response.json()["detail"]
    same = env.client.post("/api/scan", headers={"Origin": "http://testserver"})
    assert same.status_code == 202


def test_security_headers_on_every_response(env: Env) -> None:
    for path in ("/", "/api/platforms", "/static/app.css", "/missing-page"):
        response = env.client.get(path)
        assert "default-src 'self'" in response.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "same-origin"
    assert env.client.get("/").headers["cache-control"] == "no-store"
    assert "cache-control" not in env.client.get("/static/app.css").headers


def test_docs_endpoints_are_absent(env: Env) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert env.client.get(path).status_code == 404


def test_token_is_generated_once_with_private_mode(tmp_path: Path) -> None:
    first = auth.load_token(tmp_path / "data", {})
    path = auth.token_path(tmp_path / "data")
    assert path.stat().st_mode & 0o777 == 0o600
    assert len(first) >= auth.MIN_TOKEN_LENGTH
    assert auth.load_token(tmp_path / "data", {}) == first


def test_token_from_environment_wins(tmp_path: Path) -> None:
    assert auth.load_token(tmp_path, {auth.TOKEN_ENV: "e" * 20}) == "e" * 20
    assert not auth.token_path(tmp_path).exists()


def test_short_tokens_are_rejected_with_a_fix(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match=r"ROMLEDGER_TOKEN.*longer"):
        auth.load_token(tmp_path, {auth.TOKEN_ENV: "short"})
    path = auth.token_path(tmp_path)
    path.write_text("short\n")
    with pytest.raises(config.ConfigError, match=r"serve\.token.*Delete the file"):
        auth.load_token(tmp_path, {})


def test_matches_handles_missing_candidate() -> None:
    assert not auth.matches(None, "abc")
    assert auth.matches("abc", "abc")
