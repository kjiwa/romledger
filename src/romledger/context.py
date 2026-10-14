from dataclasses import dataclass
from pathlib import Path

from romledger import config, registry


@dataclass(frozen=True)
class Context:
    path: Path
    config: config.Config
    platforms: dict[str, registry.Entry]
    data_dir: Path


def load_context(config_arg: str | None) -> Context:
    path = config.resolve_path(config_arg)
    platforms = registry.load()
    loaded = config.load(path, platforms)
    config.check_library(loaded)
    return Context(path, loaded, platforms, config.data_dir())
