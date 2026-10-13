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
