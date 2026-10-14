import hmac
import os
import secrets
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from romledger.config import ConfigError

TOKEN_ENV = "ROMLEDGER_TOKEN"
TOKEN_FILE = "serve.token"
COOKIE = "romledger_session"
MIN_TOKEN_LENGTH = 16
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


SIGN_IN_HINT = (
    "Missing or invalid access token. Open the link that romledger serve prints "
    "(it ends in ?token=...), or send the token as an Authorization: Bearer header."
)
CROSS_ORIGIN = "Cross-origin requests are not allowed."


def token_path(data_dir: Path) -> Path:
    return data_dir / TOKEN_FILE


def load_token(data_dir: Path, env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    if env.get(TOKEN_ENV):
        return _checked(env[TOKEN_ENV], TOKEN_ENV)
    path = token_path(data_dir)
    try:
        return _checked(path.read_text(encoding="utf-8").strip(), str(path))
    except FileNotFoundError:
        return _create(path)


def matches(candidate: str | None, token: str) -> bool:
    return candidate is not None and hmac.compare_digest(candidate.encode(), token.encode())


def authenticate(request: Request, token: str) -> None:
    if not (_bearer_ok(request, token) or matches(request.cookies.get(COOKIE), token)):
        raise HTTPException(401, SIGN_IN_HINT)
    if request.method not in SAFE_METHODS:
        _require_same_origin(request)


def _bearer_ok(request: Request, token: str) -> bool:
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    return scheme.lower() == "bearer" and matches(value.strip(), token)


def _require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is not None and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, CROSS_ORIGIN)


def _checked(token: str, source: str) -> str:
    if len(token) < MIN_TOKEN_LENGTH:
        raise ConfigError(
            f"{source}: token is shorter than {MIN_TOKEN_LENGTH} characters. "
            f"Delete the file to generate a new one, or set a longer {TOKEN_ENV}."
        )
    return token


def _create(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(token + "\n")
    return token
