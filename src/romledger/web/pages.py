from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from romledger import state
from romledger.context import Context
from romledger.web import actions, auth, deps, upload, views
from romledger.web.render import render

router = APIRouter()

Services = Annotated[deps.Services, Depends(deps.services)]
Ctx = Annotated[Context, Depends(deps.context)]
Database = Annotated[state.State, Depends(deps.database)]
StateFilter = Literal["missing", "inbox", "have", "all"]


@router.get("/", response_model=None)
def overview(request: Request, services: Services, token: str | None = None) -> Response:
    if auth.matches(token, services.token):
        return _sign_in(request)
    context = services.context_factory()
    with state.State(context.data_dir / "state.db") as database:
        everything = views.platform_views(context, database)
    platforms = [view for view in everything if view.tracked]
    return render(request, "overview.html", platforms=platforms, scanned=_scanned(everything))


@router.get("/platforms/{slug}")
def platform(
    request: Request,
    slug: str,
    context: Ctx,
    database: Database,
    q: str = "",
    state_filter: Annotated[StateFilter, Query(alias="state")] = "missing",
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Response:
    if slug not in context.config.platforms:
        raise HTTPException(404, f"unknown platform {slug!r}")
    view = views.platform_view(context, database, slug)
    page = views.games_page(
        context,
        database,
        slug,
        [] if state_filter == "all" else [state_filter],
        q.strip(),
        offset,
    )
    params: dict[str, str | int] = {"q": q.strip(), "state": state_filter}
    path = f"/platforms/{slug}"
    previous = views.page_url(path, params, max(0, offset - page.limit)) if offset else None
    following = (
        views.page_url(path, params, offset + page.limit)
        if offset + page.limit < page.total
        else None
    )
    return render(
        request,
        "platform.html",
        platform=view,
        page=page,
        q=q.strip(),
        state=state_filter,
        previous=previous,
        following=following,
        first=offset + 1 if page.total else 0,
        last=offset + len(page.games),
    )


@router.get("/inbox")
def inbox(request: Request, context: Ctx, uploaded: Annotated[int, Query(ge=0)] = 0) -> Response:
    inboxes = context.config.library.inboxes
    return render(
        request,
        "inbox.html",
        inbox=inboxes[0],
        listing=views.list_inbox(inboxes[0]),
        set_aside=views.set_aside_counts(inboxes),
        uploaded=uploaded,
        no_refresh=True,
    )


@router.get("/activity")
def activity(request: Request, services: Services) -> Response:
    return render(request, "activity.html", records=services.jobs.history())


@router.post("/scan")
def scan_form(context: Ctx, services: Services) -> Response:
    actions.start_scan(context, services)
    return RedirectResponse("/activity", status_code=303)


@router.post("/import")
def import_form(context: Ctx, services: Services) -> Response:
    actions.start_import(context, services)
    return RedirectResponse("/activity", status_code=303)


@router.post("/inbox/upload", response_model=None)
async def upload_files(request: Request, context: Ctx, services: Services) -> Response:
    upload.refuse_while_running(services.jobs)
    saved = await upload.receive(request, context.config.library.inboxes[0])
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"saved": [{"name": item.name, "size": item.size} for item in saved]})
    return RedirectResponse(f"/inbox?uploaded={len(saved)}", status_code=303)


def _sign_in(request: Request) -> Response:
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        auth.COOKIE,
        request.query_params["token"],
        httponly=True,
        samesite="strict",
        path="/",
        secure=request.url.scheme == "https",
    )
    return response


def _scanned(platforms: list[views.PlatformView]) -> bool:
    return any(view.counts for view in platforms)
