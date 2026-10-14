import re
import unicodedata

TAGS = re.compile(r"\([^()]*\)")
SPACES = re.compile(r"\s+")
FIRST_TAG = re.compile(r"\(([^),]*)")
NOT_ALNUM = re.compile(r"[^a-z0-9]+")


def strip_tags(title: str) -> str:
    return SPACES.sub(" ", TAGS.sub("", title)).strip()


def normalize(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", strip_tags(title)).lower()
    return NOT_ALNUM.sub("", ascii_title)


def region_name(name: str) -> str:
    region = name.strip().lower()
    return "usa" if region == "world" else region


def region_of(game: str) -> str | None:
    match = FIRST_TAG.search(game)
    return None if match is None else region_name(match[1])
