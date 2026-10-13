import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rom_scraper import registry

CONFIG_ENV = "ROM_SCRAPER_CONFIG"
DATA_ENV = "ROM_SCRAPER_DATA"

REGIONS = [
    *("ARG", "ASI", "AUS", "BEL", "BRA", "CAN", "CHN", "DAN", "EUR", "FRA", "FYN", "GER"),
    *("GRE", "HK", "HOL", "ITA", "JPN", "KOR", "MEX", "NOR", "NZ", "POR", "RUS", "SPA"),
    *("SWE", "TAI", "UK", "UNK", "USA", "WORLD"),
]
LANGUAGES = [
    *("DA", "DE", "EL", "EN", "ES", "FI", "FR", "IT"),
    *("JA", "KO", "NL", "NO", "PT", "RU", "SV", "ZH"),
]

EXAMPLE = """\
[library]
roms = "/mnt/roms/roms"
inboxes = ["/mnt/roms/inbox"]

[platforms.nes]
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
    regions: tuple[str, ...] = ("USA", "WORLD")
    languages: tuple[str, ...] = ("EN",)


@dataclass(frozen=True)
class Hooks:
    after_import: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class Config:
    library: Library
    platforms: dict[str, Platform]
    hooks: Hooks = Hooks()


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


def data_dir(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if env.get(DATA_ENV):
        directory = Path(env[DATA_ENV]).expanduser()
        if not directory.is_absolute():
            raise ConfigError(f"{DATA_ENV} {env[DATA_ENV]!r} is not absolute. Use a full path.")
        return directory
    base = env.get("XDG_DATA_HOME", "")
    if not os.path.isabs(base):
        base = str(Path.home() / ".local" / "share")
    return Path(base) / "rom-scraper"


def load(path: Path, platforms_registry: Mapping[str, registry.Entry]) -> Config:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: invalid TOML ({error}). Fix the syntax.") from error
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigError(
            f"{path}: cannot read the file ({error}). Fix its permissions."
        ) from error
    _reject_unknown(path, "", data, {"library", "platforms", "hooks"})
    library = _table(path, data, "library", required=True)
    platforms = _table(path, data, "platforms", required=False)
    hooks = _table(path, data, "hooks", required=False)
    return Config(
        library=_parse_library(path, library),
        platforms={
            slug: _parse_platform(path, slug, raw, platforms_registry)
            for slug, raw in platforms.items()
        },
        hooks=_parse_hooks(path, hooks),
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
        roms=_directory(path, "library.roms", roms),
        inboxes=tuple(_directory(path, "library.inboxes", inbox) for inbox in inboxes),
    )


def _parse_hooks(path: Path, table: dict[str, Any]) -> Hooks:
    _reject_unknown(path, "hooks.", table, {"after_import"})
    commands = table.get("after_import", [])
    if not isinstance(commands, list) or not all(
        isinstance(argv, list) and argv and all(isinstance(arg, str) and arg for arg in argv)
        for argv in commands
    ):
        raise ConfigError(
            f"{path}: hooks.after_import must be a list of commands, each a non-empty list of "
            'non-empty strings, e.g. [["touch", "/mnt/roms/.imported"]].'
        )
    return Hooks(after_import=tuple(tuple(argv) for argv in commands))


def _parse_platform(
    path: Path, slug: str, raw: object, platforms_registry: Mapping[str, registry.Entry]
) -> Platform:
    key = f"platforms.{slug}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: {key} must be a table. Write it as [{key}].")
    _reject_unknown(path, f"{key}.", raw, {"dat", "regions", "languages"})
    defaults = Platform(dat="")
    return Platform(
        dat=_dat(path, slug, raw, platforms_registry),
        regions=_codes(path, raw, f"{key}.regions", "regions", defaults.regions, REGIONS),
        languages=_codes(path, raw, f"{key}.languages", "languages", defaults.languages, LANGUAGES),
    )


def _dat(
    path: Path, slug: str, raw: dict[str, Any], platforms_registry: Mapping[str, registry.Entry]
) -> str:
    key = f"platforms.{slug}.dat"
    if "dat" not in raw:
        if slug not in platforms_registry:
            raise ConfigError(
                f"{path}: unknown platform {slug!r}. Use one of: "
                f"{', '.join(sorted(platforms_registry))}; or set dat."
            )
        return platforms_registry[slug].dat
    dat = _string(path, raw, key, "dat")
    dat_set, _, name = dat.partition("/")
    if dat_set not in registry.DAT_SETS or not name:
        raise ConfigError(
            f"{path}: {key} {dat!r} must look like <{'|'.join(registry.DAT_SETS)}>/<name>."
        )
    return dat


def _directory(path: Path, dotted: str, value: str) -> Path:
    try:
        directory = Path(value).expanduser()
    except RuntimeError as error:
        raise ConfigError(f"{path}: {dotted} {value!r}: {error}. Use an absolute path.") from error
    if not directory.is_absolute():
        raise ConfigError(f"{path}: {dotted} {value!r} is not absolute. Use a full path or ~/...")
    return directory


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
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f'{path}: {dotted} must be a list of non-empty strings, e.g. ["a", "b"].')
    return tuple(value)


def _codes(
    path: Path,
    table: dict[str, Any],
    dotted: str,
    key: str,
    default: tuple[str, ...],
    allowed: list[str],
) -> tuple[str, ...]:
    codes = _strings(path, table, dotted, key, default=default)
    if not codes:
        raise ConfigError(f"{path}: {dotted} is empty. List at least one code.")
    for code in codes:
        if code not in allowed:
            hint = " Use upper case." if code.upper() in allowed else ""
            raise ConfigError(
                f"{path}: {dotted} has unknown code {code!r}.{hint} Allowed: {', '.join(allowed)}."
            )
    return codes
