import dataclasses
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from romledger import lookup, scan, state
from romledger.context import Context
from romledger.web import actions, deps, views

router = APIRouter(prefix="/api")

SHA1_PATTERN = "^[0-9a-fA-F]{40}$"
MAX_LIMIT = 1000
MAX_NAME = 300

Services = Annotated[deps.Services, Depends(deps.services)]
Ctx = Annotated[Context, Depends(deps.context)]
Database = Annotated[state.State, Depends(deps.database)]


def known_platform(context: Context, slug: str) -> None:
    if slug not in context.config.platforms:
        raise HTTPException(404, f"unknown platform {slug!r}")


@router.get("/platforms")
def platforms(context: Ctx, database: Database) -> list[dict[str, Any]]:
    return [_platform(view, context) for view in views.platform_views(context, database)]


@router.get("/platforms/{slug}/missing")
def missing(
    slug: str,
    context: Ctx,
    database: Database,
    q: str = "",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = views.PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    known_platform(context, slug)
    if database.scanned_at(slug) is None:
        raise HTTPException(409, f"{slug} has not been scanned. {scan.SCAN_HINT}")
    page = views.games_page(context, database, slug, ["missing"], q, offset, limit)
    return {
        "platform": slug,
        "total": page.total,
        "offset": offset,
        "limit": limit,
        "games": [
            {"game": game.name, "links": {"vimm": game.vimm, "emuland": game.emuland}}
            for game in page.games
        ],
    }


@router.get("/lookup")
def find(
    context: Ctx,
    database: Database,
    sha1: Annotated[str | None, Query(pattern=SHA1_PATTERN)] = None,
    name: Annotated[str | None, Query(min_length=1, max_length=MAX_NAME)] = None,
    platform: str | None = None,
    regions: Annotated[str, Query(max_length=MAX_NAME)] = "",
) -> dict[str, list[dict[str, Any]]]:
    if (sha1 is None) == (name is None):
        raise HTTPException(422, "give either sha1 or name and platform")
    if sha1 is not None:
        return {"matches": [dataclasses.asdict(match) for match in lookup.by_hash(database, sha1)]}
    if platform is None:
        raise HTTPException(422, "name needs platform")
    known_platform(context, platform)
    named = [region for region in regions.split(",") if region.strip()]
    matches = lookup.by_name(database, platform, name or "", named)
    return {"matches": [dataclasses.asdict(match) for match in matches]}


@router.get("/jobs/current")
def current_job(services: Services) -> dict[str, Any]:
    running = services.jobs.current()
    return {"job": None if running is None else dataclasses.asdict(running)}


@router.post("/scan", status_code=202)
def scan_all(context: Ctx, services: Services) -> dict[str, Any]:
    return dataclasses.asdict(actions.start_scan(context, services))


@router.post("/import", status_code=202)
def import_all(context: Ctx, services: Services) -> dict[str, Any]:
    return dataclasses.asdict(actions.start_import(context, services))


def _platform(view: views.PlatformView, context: Context) -> dict[str, Any]:
    counts = view.counts
    configured = context.config.platforms[view.slug]
    return {
        "slug": view.slug,
        "name": view.name,
        "tracked": view.tracked,
        "scanned_at": view.scanned_at,
        "wanted": view.wanted if counts else None,
        "have": counts.have if counts else None,
        "inbox": counts.inbox if counts else None,
        "missing": counts.missing if counts else None,
        "unmatched": counts.unmatched if counts else None,
        "percent": view.percent,
        "sites": {
            "vimm": views.site_code(context, view.slug, "vimm"),
            "coolrom": configured.coolrom,
            "consoleroms": views.site_code(context, view.slug, "consoleroms"),
            "emuland": views.site_code(context, view.slug, "emuland"),
        },
    }
