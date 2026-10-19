import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from romledger import DOCS_URL, catalog, http, registry

CONFIG_ENV = "ROMLEDGER_CONFIG"
DATA_ENV = "ROMLEDGER_DATA"

REGIONS = [
    *("ARG", "ASI", "AUS", "BEL", "BRA", "CAN", "CHN", "DAN", "EUR", "FRA", "FYN", "GER"),
    *("GRE", "HK", "HOL", "ITA", "JPN", "KOR", "MEX", "NOR", "NZ", "POR", "RUS", "SPA"),
    *("SWE", "TAI", "UK", "UNK", "USA", "WORLD"),
]
LANGUAGES = [
    *("DA", "DE", "EL", "EN", "ES", "FI", "FR", "IT"),
    *("JA", "KO", "NL", "NO", "PT", "RU", "SV", "ZH"),
]

WANTED_KEYS = {"regions", "languages", "include"}
REMOVED_PLATFORM_KEYS = {
    "dat": "romledger picks each platform's DAT",
    "sources": "fetch uses every source that carries the platform",
    "archive_item": "the Internet Archive is no longer a source",
}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Library:
    roms: Path
    inboxes: tuple[Path, ...]


@dataclass(frozen=True)
class Wanted:
    regions: tuple[str, ...] = ("USA", "WORLD")
    languages: tuple[str, ...] = ("EN",)
    include: tuple[str, ...] = ()


@dataclass(frozen=True)
class Platform:
    dat: str
    regions: tuple[str, ...] = Wanted.regions
    languages: tuple[str, ...] = Wanted.languages
    include: tuple[str, ...] = Wanted.include
    consoleroms: str | None = None


@dataclass(frozen=True)
class Hooks:
    after_import: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class Network:
    proxy: str | None = None


@dataclass(frozen=True)
class Config:
    library: Library
    platforms: dict[str, Platform]
    hooks: Hooks = Hooks()
    network: Network = Network()
    wanted: Wanted = Wanted()


def config_path(arg: str | None, env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if arg:
        return Path(arg).expanduser()
    if env.get(CONFIG_ENV):
        return Path(env[CONFIG_ENV]).expanduser()
    base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "romledger" / "config.toml"


def resolve_path(arg: str | None, env: Mapping[str, str] | None = None) -> Path:
    path = config_path(arg, env)
    if not path.is_file():
        raise ConfigError(
            f"{path}: config file not found. Run `romledger init` to create it, "
            f"or pass --config or set {CONFIG_ENV}."
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
    return Path(base) / "romledger"


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
    _reject_unknown(path, "", data, {"library", "wanted", "platforms", "hooks", "network"})
    library = _table(path, data, "library", required=True)
    wanted = _parse_wanted(path, _table(path, data, "wanted", required=False))
    overrides = _table(path, data, "platforms", required=False)
    hooks = _table(path, data, "hooks", required=False)
    network = _table(path, data, "network", required=False)
    for slug in overrides:
        if slug not in platforms_registry:
            raise ConfigError(
                f"{path}: platforms.{slug}: {registry.unknown(slug, platforms_registry)}"
            )
    return Config(
        library=_parse_library(path, library),
        platforms={
            slug: _parse_platform(path, slug, overrides.get(slug, {}), entry, wanted)
            for slug, entry in platforms_registry.items()
        },
        hooks=_parse_hooks(path, hooks),
        network=_parse_network(path, network),
        wanted=wanted,
    )


def check_library(config: Config) -> None:
    _require_directory(config.library.roms)
    for inbox in config.library.inboxes:
        if not inbox.is_dir() and inbox.parent.is_dir():
            _create_directory(inbox)
        _require_directory(inbox)


def _create_directory(directory: Path) -> None:
    try:
        directory.mkdir()
    except OSError as error:
        raise ConfigError(
            f"{directory}: cannot create: {error.strerror}. Check its permissions."
        ) from error


def _require_directory(directory: Path) -> None:
    if not directory.is_dir():
        raise ConfigError(
            f"{directory}: not a directory. Is the drive or share mounted? "
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
            'non-empty strings, e.g. [["touch", "/path/to/roms/.imported"]].'
        )
    return Hooks(after_import=tuple(tuple(argv) for argv in commands))


def _parse_network(path: Path, table: dict[str, Any]) -> Network:
    _reject_unknown(path, "network.", table, {"proxy"})
    if "proxy" not in table:
        return Network()
    proxy = _string(path, table, "network.proxy", "proxy")
    _check_proxy(path, proxy)
    return Network(proxy=proxy)


def _check_proxy(path: Path, proxy: str) -> None:
    try:
        parts = urlsplit(proxy)
        _ = parts.port
    except ValueError as error:
        raise ConfigError(f"{path}: network.proxy is not a valid URL ({error}).") from error
    if parts.scheme not in http.PROXY_SCHEMES or not parts.hostname:
        raise ConfigError(
            f"{path}: network.proxy {http.redact(proxy)!r} must be <scheme>://[user@]host[:port] "
            f"with scheme one of: {', '.join(http.PROXY_SCHEMES)}."
        )


def _parse_wanted(path: Path, table: dict[str, Any]) -> Wanted:
    _reject_unknown(path, "wanted.", table, WANTED_KEYS)
    return _wanted(path, "wanted", table, Wanted())


def _parse_platform(
    path: Path, slug: str, raw: object, entry: registry.Entry, defaults: Wanted
) -> Platform:
    key = f"platforms.{slug}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: {key} must be a table. Write it as [{key}].")
    for removed, reason in REMOVED_PLATFORM_KEYS.items():
        if removed in raw:
            raise ConfigError(f"{path}: {key}.{removed} was removed in 0.6. Delete it: {reason}.")
    _reject_unknown(path, f"{key}.", raw, WANTED_KEYS)
    wanted = _wanted(path, key, raw, defaults)
    return Platform(
        dat=entry.dat,
        regions=wanted.regions,
        languages=wanted.languages,
        include=wanted.include,
        consoleroms=entry.consoleroms,
    )


def _wanted(path: Path, key: str, raw: dict[str, Any], defaults: Wanted) -> Wanted:
    return Wanted(
        regions=_codes(path, raw, f"{key}.regions", "regions", defaults.regions, REGIONS),
        languages=_codes(path, raw, f"{key}.languages", "languages", defaults.languages, LANGUAGES),
        include=_include(path, raw, key, defaults.include),
    )


def _include(
    path: Path, raw: dict[str, Any], key: str, default: tuple[str, ...]
) -> tuple[str, ...]:
    names = _strings(path, raw, f"{key}.include", "include", default=default)
    for name in names:
        if name not in catalog.CATEGORIES:
            raise ConfigError(
                f"{path}: {key}.include has unknown category {name!r}. "
                f"Allowed: {', '.join(catalog.CATEGORIES)}."
            )
    return tuple(dict.fromkeys(names))


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
            raise ConfigError(f"{path}: missing [{name}] table. Add it; see {DOCS_URL}/setup.md.")
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
