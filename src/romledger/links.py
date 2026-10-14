from urllib.parse import quote_plus

from romledger.titles import strip_tags

VIMM_URL = "https://vimm.net/vault/?p=list&system={system}&q={query}"
MIN_QUERY = 3


def vimm_search(system: str, game: str) -> str | None:
    query = strip_tags(game)
    if len(query) < MIN_QUERY:
        return None
    return VIMM_URL.format(system=system, query=quote_plus(query))
