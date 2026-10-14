import re
import unicodedata

TAGS = re.compile(r"\s*\([^)]*\)")
FIRST_TAG = re.compile(r"\(([^),]*)")
NOT_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", TAGS.sub("", title)).lower()
    return NOT_ALNUM.sub("", ascii_title)


def region_of(game: str) -> str | None:
    match = FIRST_TAG.search(game)
    if match is None:
        return None
    region = match[1].strip().lower()
    return "usa" if region == "world" else region
