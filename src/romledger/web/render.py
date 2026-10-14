from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from romledger import DOCS_URL, __version__
from romledger.web import deps, views

ROOT = Path(__file__).parent
TEMPLATE_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"


def _globals(request: Request) -> dict[str, Any]:
    return {
        "job": deps.services(request).jobs.current(),
        "auto_import": deps.services(request).auto_import,
        "version": __version__,
        "docs_url": DOCS_URL,
        "path": request.url.path,
    }


templates = Jinja2Templates(directory=TEMPLATE_DIR, context_processors=[_globals])
templates.env.filters["size"] = views.human_size
templates.env.filters["stamp"] = views.stamp
templates.env.filters["number"] = "{:,}".format
templates.env.globals["duration"] = views.duration


def render(request: Request, name: str, status: int = 200, **context: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, name, context, status_code=status)
