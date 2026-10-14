from urllib.parse import quote_plus

from romledger.titles import TAGS

VIMM_URL = "https://vimm.net/vault/?p=list&system={system}&q={query}"
ARCHIVE_URL = "https://archive.org/search?query={query}"
MIN_QUERY = 3


def vimm_search(system: str, game: str) -> str | None:
    query = TAGS.sub("", game).strip()
    if len(query) < MIN_QUERY:
        return None
    return VIMM_URL.format(system=system, query=quote_plus(query))


def archive_search(game: str) -> str:
    query = TAGS.sub("", game).strip() or game
    return ARCHIVE_URL.format(query=quote_plus(query))
