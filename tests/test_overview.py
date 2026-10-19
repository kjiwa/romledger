from pathlib import Path

from romledger import config, overview, registry, state
from romledger.context import Context


def make_context(tmp_path: Path) -> Context:
    entries = registry.load()
    cfg = config.Config(
        config.Library(tmp_path / "roms", (tmp_path / "inbox",)),
        {slug: config.Platform(entries[slug].dat) for slug in ("nes", "snes")},
    )
    return Context(tmp_path / "config.toml", cfg, entries, tmp_path / "data")


def test_rows_describe_every_platform(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    items = [
        state.Item("A", "have", "/a"),
        state.Item("B", "missing", None),
        state.Item("C", "inbox", "/c"),
    ]
    with state.State(tmp_path / "data" / "state.db") as database:
        database.replace_platform("nes", items, ["/u"], "1", "2026-10-13T12:00:00+00:00")
        rows = overview.platform_rows(context, database)
    nes, snes = rows
    assert nes == {
        "slug": "nes",
        "name": "Nintendo - Nintendo Entertainment System",
        "tracked": True,
        "scanned_at": "2026-10-13T12:00:00+00:00",
        "wanted": 3,
        "have": 1,
        "inbox": 1,
        "missing": 1,
        "unmatched": 1,
        "percent": 33,
        "sites": {"vimm": "NES", "consoleroms": "nes"},
    }
    assert snes["tracked"] is False
    assert (snes["wanted"], snes["have"], snes["percent"], snes["scanned_at"]) == (
        None,
        None,
        None,
        None,
    )


def test_a_scanned_platform_without_games_is_not_tracked(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    with state.State(tmp_path / "data" / "state.db") as database:
        database.replace_platform("nes", [state.Item("A", "missing", None)], [], "1", "t")
        row = overview.platform_rows(context, database)[0]
    assert (row["tracked"], row["wanted"], row["percent"]) == (False, 1, 0)


def test_a_scanned_empty_dat_has_no_percent(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    with state.State(tmp_path / "data" / "state.db") as database:
        database.replace_platform("nes", [], [], "1", "t")
        row = overview.platform_rows(context, database)[0]
    assert (row["wanted"], row["percent"]) == (0, None)


def test_sites_are_null_for_a_platform_outside_the_registry(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    context.platforms.pop("nes")
    with state.State(tmp_path / "data" / "state.db") as database:
        assert overview.platform_rows(context, database)[0]["sites"] == {
            "vimm": None,
            "consoleroms": None,
        }
