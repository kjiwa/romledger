from typing import Any

from romledger import state
from romledger.context import Context
from romledger.sources import SOURCES


def platform_rows(context: Context, database: state.State) -> list[dict[str, Any]]:
    counts = database.counts()
    return [_row(context, database, slug, counts.get(slug)) for slug in context.config.platforms]


def _row(
    context: Context, database: state.State, slug: str, counts: state.Counts | None
) -> dict[str, Any]:
    wanted = counts.have + counts.inbox + counts.missing if counts else 0
    entry = context.platforms.get(slug)
    return {
        "slug": slug,
        "name": context.config.platforms[slug].dat.split("/", 1)[-1],
        "tracked": counts is not None and counts.has_games,
        "scanned_at": database.scanned_at(slug),
        "wanted": wanted if counts else None,
        "have": counts.have if counts else None,
        "inbox": counts.inbox if counts else None,
        "missing": counts.missing if counts else None,
        "unmatched": counts.unmatched if counts else None,
        "percent": counts.have * 100 // wanted if counts and wanted else None,
        "sites": {name: getattr(entry, name, None) for name in SOURCES},
    }
