from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from romledger import igir, importer
from romledger.config import ConfigError
from romledger.web import api, deps, pages, render, upload

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
TITLES = {
    400: "Request refused",
    401: "Sign in required",
    403: "Request blocked",
    404: "Not found",
    409: "Busy",
    415: "Unsupported upload",
    422: "Invalid request",
    500: "Something went wrong",
    503: "Library unavailable",
}


def create_app(
    context_factory: deps.ContextFactory,
    token: str,
    *,
    igir_report: Any = igir.report,
    igir_move: Any = igir.move,
    hook: Any = importer.run_hook,
) -> FastAPI:
    app = FastAPI(
        title="romledger",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        dependencies=[Depends(deps.guard)],
    )
    app.state.services = deps.Services(
        context_factory, token, deps.Tools(igir_report, igir_move, hook)
    )
    app.include_router(pages.router)
    app.include_router(api.router)
    app.mount("/static", StaticFiles(directory=render.STATIC_DIR), name="static")
    app.middleware("http")(_secure)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _invalid)
    app.add_exception_handler(ConfigError, _config_error)
    app.add_exception_handler(upload.UploadError, _upload_error)
    app.add_exception_handler(Exception, _unexpected)
    return app


async def _secure(request: Request, call_next: Any) -> Response:
    response: Response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    if not request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def _failure(request: Request, status: int, message: str, headers: dict[str, str]) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": message}, status_code=status, headers=headers)
    page = render.render(
        request,
        "error.html",
        status,
        code=status,
        title=TITLES.get(status, "Error"),
        message=message,
        bare=status == 401,
    )
    page.headers.update(headers)
    return page


def _http_error(request: Request, error: Exception) -> Response:
    assert isinstance(error, HTTPException)
    headers = {"WWW-Authenticate": "Bearer"} if error.status_code == 401 else {}
    return _failure(request, error.status_code, str(error.detail), headers)


async def _invalid(request: Request, error: Exception) -> Response:
    assert isinstance(error, RequestValidationError)
    if request.url.path.startswith("/api/"):
        return await request_validation_exception_handler(request, error)
    fields = ", ".join(str(item["loc"][-1]) for item in error.errors())
    return _failure(request, 422, f"Check the value of: {fields}.", {})


def _config_error(request: Request, error: Exception) -> Response:
    return _failure(request, 503, str(error), {})


def _upload_error(request: Request, error: Exception) -> Response:
    assert isinstance(error, upload.UploadError)
    return _failure(request, error.status, str(error), {})


def _unexpected(request: Request, error: Exception) -> Response:
    message = "Something unexpected happened. Check the server log."
    if request.url.path.startswith("/api/"):
        response: Response = JSONResponse({"error": message}, status_code=500)
    else:
        response = _failure(request, 500, message, {})
    response.headers.update(SECURITY_HEADERS)
    response.headers["Cache-Control"] = "no-store"
    return response
