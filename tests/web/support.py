from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from romledger import config, datindex, dats, registry, state
from romledger.context import Context
from romledger.web.deps import Services

TOKEN = "t" * 32
SCANNED_AT = "2026-10-13T12:00:00+00:00"
GAMES = {"Alpha (USA)": "a", "Beta (USA)": "b", "Cat (USA)": "c", "Dog (Japan)": "d"}
DAT = 'clrmamepro (\n\tversion "1"\n)\n' + "".join(
    f'game (\n\tname "{name}"\n\trom ( name "{name}.nes" size 1 sha1 {letter * 40} )\n)\n'
    for name, letter in GAMES.items()
)


@dataclass
class Env:
    context: Context
    inbox: Path
    data: Path
    client: TestClient
    reports: list[str]
    moves: list[str]
    services: Services

    def bearer(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {TOKEN}"}


def make_context(tmp_path: Path) -> Context:
    roms, inbox, data = tmp_path / "roms", tmp_path / "inbox", tmp_path / "data"
    roms.mkdir()
    inbox.mkdir()
    platforms = registry.load()
    cfg = config.Config(
        config.Library(roms, (inbox,)), {"nes": config.Platform(platforms["nes"].dat)}
    )
    dat = dats.dat_path(data, cfg.platforms["nes"].dat)
    dat.parent.mkdir(parents=True)
    dat.write_text(DAT)
    return Context(tmp_path / "config.toml", cfg, platforms, data)


def seed(context: Context) -> None:
    dat = dats.dat_path(context.data_dir, context.config.platforms["nes"].dat)
    items = [
        state.Item("Alpha (USA)", "have", "/a"),
        state.Item("Beta (USA)", "missing", None),
        state.Item("Cat (USA)", "inbox", "/c"),
    ]
    with state.State(context.data_dir / "state.db") as database:
        database.replace_platform("nes", items, [], "1", SCANNED_AT)
        datindex.ensure(database, "nes", dat)
