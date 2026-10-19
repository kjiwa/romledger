from romledger import registry
from romledger.sources import SOURCES, consoleroms


def test_only_consoleroms_is_fetched_from_the_command_line() -> None:
    assert {name: info.fetch for name, info in SOURCES.items()} == {
        "vimm": False,
        "consoleroms": True,
    }


def test_the_registry_agrees_with_the_source_modules() -> None:
    assert SOURCES["consoleroms"].hosts == consoleroms.HOSTS


def test_every_source_has_a_code_column_in_the_platform_table() -> None:
    entry = next(iter(registry.load().values()))
    assert all(hasattr(entry, name) for name in SOURCES)
    assert tuple(SOURCES) == registry.SITES
