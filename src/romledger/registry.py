import difflib
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files

DAT_SETS = ("no-intro", "redump")
IGNORE_TABLE = "ignore"
SITES = ("vimm", "coolrom", "consoleroms", "emuland")


@dataclass(frozen=True)
class Entry:
    slug: str
    dat: str
    vimm: str | None = None
    coolrom: str | None = None
    consoleroms: str | None = None
    emuland: str | None = None


def load() -> dict[str, Entry]:
    return {slug: _entry(slug, raw) for slug, raw in _parse().items() if slug != IGNORE_TABLE}


def ignored() -> dict[str, frozenset[str]]:
    raw = _parse().get(IGNORE_TABLE, {})
    if not isinstance(raw, dict):
        raise ValueError(f"platforms.toml: {IGNORE_TABLE} must be a table")
    unknown = set(raw) - set(SITES)
    if unknown:
        raise ValueError(f"platforms.toml: {IGNORE_TABLE}: unknown keys {sorted(unknown)}")
    return {site: _codes(site, raw.get(site, [])) for site in SITES}


def unknown(slug: str, entries: Mapping[str, Entry]) -> str:
    near = difflib.get_close_matches(slug, entries, n=3, cutoff=0.5)
    hint = f"Nearest: {', '.join(near)}." if near else "Run romledger platforms to list them."
    return f"unknown platform {slug!r}. {hint}"


def _parse() -> dict[str, object]:
    text = files("romledger").joinpath("platforms.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


def _codes(site: str, value: object) -> frozenset[str]:
    if not isinstance(value, list) or not all(isinstance(code, str) and code for code in value):
        raise ValueError(
            f"platforms.toml: {IGNORE_TABLE}.{site} must be a list of non-empty strings"
        )
    return frozenset(value)


def _entry(slug: str, raw: object) -> Entry:
    if not isinstance(raw, dict):
        raise ValueError(f"platforms.toml: {slug} must be a table")
    unknown = set(raw) - {"dat", *SITES}
    if unknown:
        raise ValueError(f"platforms.toml: {slug}: unknown keys {sorted(unknown)}")
    dat = raw.get("dat")
    if not isinstance(dat, str) or dat.split("/", 1)[0] not in DAT_SETS:
        raise ValueError(f"platforms.toml: {slug}: dat must be '<{'|'.join(DAT_SETS)}>/<name>'")
    return Entry(slug, dat, *(_optional(slug, raw, site) for site in SITES))


def _optional(slug: str, raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError(f"platforms.toml: {slug}: {key} must be a non-empty string")
    return value
