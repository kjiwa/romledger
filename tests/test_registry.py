from importlib.resources import files

import pytest

from romledger import registry


def test_data_file_is_packaged() -> None:
    assert files("romledger").joinpath("platforms.toml").is_file()


def test_load_entries() -> None:
    entries = registry.load()
    nes = entries["nes"]
    assert nes.slug == "nes"
    assert nes.dat == "no-intro/Nintendo - Nintendo Entertainment System"
    assert nes.vimm == "NES"
    assert nes.coolrom is None


def test_every_dat_has_valid_set() -> None:
    for entry in registry.load().values():
        assert entry.dat.split("/", 1)[0] in registry.DAT_SETS
        assert entry.dat.split("/", 1)[1]


def test_slugs_and_dats_unique() -> None:
    entries = registry.load()
    assert len({entry.dat for entry in entries.values()}) == len(entries)


@pytest.mark.parametrize(
    "raw",
    [1, {}, {"dat": "other/x"}, {"dat": "redump/x", "vimm": 1}, {"dat": "redump/x", "bogus": "y"}],
)
def test_invalid_entry_names_slug(raw: object) -> None:
    with pytest.raises(ValueError, match=r"platforms\.toml: bad"):
        registry._entry("bad", raw)


def test_ignore_table_is_not_a_platform() -> None:
    assert "ignore" not in registry.load()


def test_ignored_codes() -> None:
    ignored = registry.ignored()
    assert ignored["vimm"] == {"WiiWare", "X360-D"}
    assert "mame" in ignored["coolrom"]


def test_no_ignored_code_is_also_mapped() -> None:
    entries = registry.load().values()
    ignored = registry.ignored()
    assert not ignored["vimm"] & {entry.vimm for entry in entries}
    assert not ignored["coolrom"] & {entry.coolrom for entry in entries}


def test_ignored_defaults_to_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_parse", lambda: {})
    assert registry.ignored() == {"vimm": frozenset(), "coolrom": frozenset()}


@pytest.mark.parametrize(
    ("table", "message"),
    [
        (1, "ignore must be a table"),
        ({"gog": ["x"]}, r"ignore: unknown keys \['gog'\]"),
        ({"vimm": "WiiWare"}, r"ignore\.vimm must be a list"),
        ({"vimm": [""]}, r"ignore\.vimm must be a list"),
        ({"coolrom": [1]}, r"ignore\.coolrom must be a list"),
    ],
)
def test_invalid_ignore_table(monkeypatch: pytest.MonkeyPatch, table: object, message: str) -> None:
    monkeypatch.setattr(registry, "_parse", lambda: {"ignore": table})
    with pytest.raises(ValueError, match=message):
        registry.ignored()
