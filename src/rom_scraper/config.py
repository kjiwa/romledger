import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_ENV = "ROM_SCRAPER_CONFIG"

EXAMPLE = """\
[library]
roms = "/mnt/roms/roms"
inboxes = ["/mnt/roms/inbox"]

[platforms.nes]
dat = "no-intro/Nintendo - Nintendo Entertainment System"
"""


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Library:
    roms: Path
    inboxes: tuple[Path, ...]


@dataclass(frozen=True)
class Platform:
    dat: str
    regions: tuple[str, ...] = ("USA", "World")
    languages: tuple[str, ...] = ("En",)


@dataclass(frozen=True)
class Config:
    library: Library
    platforms: dict[str, Platform]


def resolve_path(arg: str | None, env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if arg:
        path = Path(arg).expanduser()
    elif env.get(CONFIG_ENV):
        path = Path(env[CONFIG_ENV]).expanduser()
    else:
        base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        path = Path(base) / "rom-scraper" / "config.toml"
    if not path.is_file():
        raise ConfigError(
            f"{path}: config file not found. Pass --config, set {CONFIG_ENV}, "
            f"or create the file. Minimal example:\n\n{EXAMPLE}"
        )
    return path


def load(path: Path) -> Config:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: invalid TOML ({error}). Fix the syntax.") from error
    _reject_unknown(path, "", data, {"library", "platforms"})
    library = _table(path, data, "library", required=True)
    platforms = _table(path, data, "platforms", required=False)
    return Config(
        library=_parse_library(path, library),
        platforms={slug: _parse_platform(path, slug, raw) for slug, raw in platforms.items()},
    )


def check_library(config: Config) -> None:
    for directory in (config.library.roms, *config.library.inboxes):
        if not directory.is_dir():
            raise ConfigError(
                f"{directory}: not a directory. Is the NAS share mounted? "
                "Mount it, or fix the path in the config file."
            )


def _parse_library(path: Path, table: dict[str, Any]) -> Library:
    _reject_unknown(path, "library.", table, {"roms", "inboxes"})
    roms = _string(path, table, "library.roms", "roms")
    inboxes = _strings(path, table, "library.inboxes", "inboxes", default=None)
    if not inboxes:
        raise ConfigError(f"{path}: library.inboxes is empty. List at least one inbox directory.")
    return Library(
        roms=Path(roms).expanduser(),
        inboxes=tuple(Path(inbox).expanduser() for inbox in inboxes),
    )


def _parse_platform(path: Path, slug: str, raw: object) -> Platform:
    key = f"platforms.{slug}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: {key} must be a table. Write it as [{key}].")
    _reject_unknown(path, f"{key}.", raw, {"dat", "regions", "languages"})
    defaults = Platform(dat="")
    return Platform(
        dat=_string(path, raw, f"{key}.dat", "dat"),
        regions=_strings(path, raw, f"{key}.regions", "regions", default=defaults.regions),
        languages=_strings(path, raw, f"{key}.languages", "languages", default=defaults.languages),
    )


def _table(path: Path, data: dict[str, Any], name: str, *, required: bool) -> dict[str, Any]:
    if name not in data:
        if required:
            raise ConfigError(f"{path}: missing [{name}] table. Add it; see the example in README.")
        return {}
    value = data[name]
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: {name} must be a table. Write it as [{name}].")
    return value


def _reject_unknown(path: Path, prefix: str, table: dict[str, Any], allowed: set[str]) -> None:
    for key in table:
        if key not in allowed:
            raise ConfigError(
                f"{path}: unknown key {prefix}{key}. "
                f"Remove it; allowed keys: {', '.join(sorted(allowed))}."
            )


def _string(path: Path, table: dict[str, Any], dotted: str, key: str) -> str:
    if key not in table:
        raise ConfigError(f"{path}: missing {dotted}. Add it as a string.")
    value = table[key]
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{path}: {dotted} must be a non-empty string. Quote the value.")
    return value


def _strings(
    path: Path,
    table: dict[str, Any],
    dotted: str,
    key: str,
    *,
    default: tuple[str, ...] | None,
) -> tuple[str, ...]:
    if key not in table:
        if default is None:
            raise ConfigError(f"{path}: missing {dotted}. Add it as a list of strings.")
        return default
    value = table[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f'{path}: {dotted} must be a list of strings, e.g. ["a", "b"].')
    return tuple(value)
