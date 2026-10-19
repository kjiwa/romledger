import re
from collections.abc import Iterable
from dataclasses import dataclass

from romledger import titles

EXCLUSIONS = {
    "unlicensed": "Unl|Pirate",
    "aftermarket": "Aftermarket|Homebrew",
    "prerelease": "Proto|Beta|Demo|Sample|Kiosk|Debug",
    "programs": "Program|Test Program",
    "bad": r"b\d*",
}
CATEGORIES = tuple(EXCLUSIONS)
LEADING_WORDS = r"(?:\S+ )*"
EXCLUDED = {
    category: re.compile(rf"{'' if category == 'bad' else LEADING_WORDS}(?:{names})(?: \S+)*")
    for category, names in EXCLUSIONS.items()
}
TAG = re.compile(r"[(\[]([^()\[\]]*)[)\]]")
PAREN_TAG = re.compile(r"\(([^()]*)\)")
PART = re.compile(r"Disc \d+|Track \d+|Side [A-Z]|Part \d+")
REVISION = re.compile(r"Rev (\w+)|v(\d+(?:\.\d+)*)")
REGION_CODES = {
    "Argentina": "ARG",
    "Asia": "ASI",
    "Australia": "AUS",
    "Belgium": "BEL",
    "Brazil": "BRA",
    "Canada": "CAN",
    "China": "CHN",
    "Denmark": "DAN",
    "Europe": "EUR",
    "Finland": "FYN",
    "France": "FRA",
    "Germany": "GER",
    "Greece": "GRE",
    "Hong Kong": "HK",
    "Italy": "ITA",
    "Japan": "JPN",
    "Korea": "KOR",
    "Mexico": "MEX",
    "Netherlands": "HOL",
    "New Zealand": "NZ",
    "Norway": "NOR",
    "Portugal": "POR",
    "Russia": "RUS",
    "Spain": "SPA",
    "Sweden": "SWE",
    "Taiwan": "TAI",
    "UK": "UK",
    "United Kingdom": "UK",
    "Unknown": "UNK",
    "USA": "USA",
    "World": "WORLD",
}
LANGUAGE_CODES = {
    "Da": "DA",
    "De": "DE",
    "El": "EL",
    "En": "EN",
    "Es": "ES",
    "Fi": "FI",
    "Fr": "FR",
    "It": "IT",
    "Ja": "JA",
    "Ko": "KO",
    "Nl": "NL",
    "No": "NO",
    "Pt": "PT",
    "Ru": "RU",
    "Sv": "SV",
    "Zh": "ZH",
}
IMPLIED_LANGUAGES = {
    **dict.fromkeys(("USA", "WORLD", "EUR", "UK", "AUS", "CAN", "NZ"), "EN"),
    **dict.fromkeys(("ARG", "MEX", "SPA"), "ES"),
    **dict.fromkeys(("CHN", "HK", "TAI"), "ZH"),
    **dict.fromkeys(("BRA", "POR"), "PT"),
    "DAN": "DA",
    "FRA": "FR",
    "FYN": "FI",
    "GER": "DE",
    "GRE": "EL",
    "HOL": "NL",
    "ITA": "IT",
    "JPN": "JA",
    "KOR": "KO",
    "NOR": "NO",
    "RUS": "RU",
    "SWE": "SV",
}


@dataclass(frozen=True)
class Game:
    name: str
    roms: tuple[str, ...]


@dataclass(frozen=True)
class Group:
    members: tuple[str, ...]

    @property
    def preferred(self) -> str:
        return self.members[0]


@dataclass(frozen=True)
class Release:
    name: str
    regions: tuple[str, ...]
    languages: tuple[str, ...]
    extras: int
    revision: tuple[tuple[int, int], ...]


def wanted_groups(
    games: Iterable[Game],
    regions: tuple[str, ...],
    languages: tuple[str, ...],
    include: tuple[str, ...],
) -> list[Group]:
    excluded = [EXCLUDED[category] for category in CATEGORIES if category not in include]
    groups: dict[str, list[Release]] = {}
    for game in games:
        release = _release(game.name)
        if _is_wanted(game, release, excluded, regions, languages):
            groups.setdefault(_key(game.name), []).append(release)
    return [_group(releases, regions, languages) for _, releases in sorted(groups.items())]


def _is_wanted(
    game: Game,
    release: Release,
    excluded: list[re.Pattern[str]],
    regions: tuple[str, ...],
    languages: tuple[str, ...],
) -> bool:
    return (
        not _is_excluded((game.name, *game.roms), excluded)
        and bool(set(release.regions) & set(regions))
        and bool(set(release.languages) & set(languages))
    )


def _is_excluded(names: Iterable[str], excluded: list[re.Pattern[str]]) -> bool:
    return any(
        pattern.fullmatch(part)
        for name in names
        for tag in TAG.findall(name)
        for part in tag.split(", ")
        for pattern in excluded
    )


def _key(name: str) -> str:
    parts = "".join(tag for tag in PAREN_TAG.findall(name) if PART.fullmatch(tag))
    return (titles.normalize(name) or titles.strip_tags(name).lower()) + parts.lower()


def _release(name: str) -> Release:
    tags = PAREN_TAG.findall(name)
    regions = _regions(tags[0]) if tags else ()
    explicit = _explicit_languages(tags[1:])
    implied = tuple(
        dict.fromkeys(
            IMPLIED_LANGUAGES[region] for region in regions if region in IMPLIED_LANGUAGES
        )
    )
    revision = _revision(tags)
    extras = sum(1 for tag in tags[1:] if not _is_identity(tag))
    return Release(name, regions, explicit or implied, extras, revision)


def _is_identity(tag: str) -> bool:
    return bool(_explicit_languages([tag]) or REVISION.fullmatch(tag) or PART.fullmatch(tag))


def _regions(tag: str) -> tuple[str, ...]:
    return tuple(REGION_CODES[name] for name in tag.split(", ") if name in REGION_CODES)


def _explicit_languages(tags: Iterable[str]) -> tuple[str, ...]:
    for tag in tags:
        codes = [LANGUAGE_CODES.get(token.partition("-")[0]) for token in tag.split(",")]
        if all(codes):
            return tuple(code for code in codes if code)
    return ()


def _revision(tags: Iterable[str]) -> tuple[tuple[int, int], ...]:
    for tag in tags:
        if (match := REVISION.fullmatch(tag)) is not None:
            if match[2] is not None:
                return tuple((0, int(part)) for part in match[2].split("."))
            if match[1].isdigit():
                return ((0, int(match[1])),)
            return tuple((1, ord(letter) - 64) for letter in match[1])
    return ()


def _group(releases: list[Release], regions: tuple[str, ...], languages: tuple[str, ...]) -> Group:
    ordered = sorted(releases, key=lambda release: release.name)
    ordered.sort(key=lambda release: release.revision, reverse=True)
    ordered.sort(
        key=lambda release: (
            _rank(release.regions, regions),
            _rank(release.languages, languages),
            release.extras,
        )
    )
    return Group(tuple(release.name for release in ordered))


def _rank(have: tuple[str, ...], preference: tuple[str, ...]) -> int:
    return min(
        (preference.index(code) for code in have if code in preference), default=len(preference)
    )
