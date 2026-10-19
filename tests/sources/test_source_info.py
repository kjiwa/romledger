from romledger import registry
from romledger.sources import HASH, SOURCES, TITLE, consoleroms


def test_a_source_is_either_fetched_or_used_from_the_browser() -> None:
    assert {name: (info.fetch, info.browser) for name, info in SOURCES.items()} == {
        "vimm": (False, True),
        "consoleroms": (True, False),
    }


def test_only_a_site_that_publishes_hashes_matches_by_hash() -> None:
    assert {name: info.match for name, info in SOURCES.items()} == {
        "vimm": HASH,
        "consoleroms": TITLE,
    }


def test_the_registry_agrees_with_the_source_modules() -> None:
    assert SOURCES["consoleroms"].name == consoleroms.NAME
    assert SOURCES["consoleroms"].hosts == consoleroms.HOSTS


def test_every_source_has_a_code_column_in_the_platform_table() -> None:
    entry = next(iter(registry.load().values()))
    assert all(hasattr(entry, name) for name in SOURCES)
    assert tuple(SOURCES) == registry.SITES
