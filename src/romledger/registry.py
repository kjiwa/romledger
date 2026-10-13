import tomllib
from dataclasses import dataclass
from importlib.resources import files

DAT_SETS = ("no-intro", "redump")


@dataclass(frozen=True)
class Entry:
    slug: str
    dat: str
    vimm: str | None = None
    coolrom: str | None = None


def load() -> dict[str, Entry]:
    text = files("romledger").joinpath("platforms.toml").read_text(encoding="utf-8")
    return {slug: _entry(slug, raw) for slug, raw in tomllib.loads(text).items()}


def _entry(slug: str, raw: object) -> Entry:
    if not isinstance(raw, dict):
        raise ValueError(f"platforms.toml: {slug} must be a table")
    unknown = set(raw) - {"dat", "vimm", "coolrom"}
    if unknown:
        raise ValueError(f"platforms.toml: {slug}: unknown keys {sorted(unknown)}")
    dat = raw.get("dat")
    if not isinstance(dat, str) or dat.split("/", 1)[0] not in DAT_SETS:
        raise ValueError(f"platforms.toml: {slug}: dat must be '<{'|'.join(DAT_SETS)}>/<name>'")
    return Entry(slug, dat, _optional(slug, raw, "vimm"), _optional(slug, raw, "coolrom"))


def _optional(slug: str, raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError(f"platforms.toml: {slug}: {key} must be a non-empty string")
    return value
