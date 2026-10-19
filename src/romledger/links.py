from urllib.parse import quote_plus

from romledger.titles import strip_tags

VIMM_URL = "https://vimm.net/vault/?p=list&system={system}&q={query}"
MIN_QUERY = 3


def _query(game: str) -> str | None:
    query = strip_tags(game)
    return quote_plus(query) if len(query) >= MIN_QUERY else None


def vimm_search(system: str, game: str) -> str | None:
    query = _query(game)
    return VIMM_URL.format(system=system, query=query) if query else None
