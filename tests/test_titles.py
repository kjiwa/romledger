import time

import pytest

from romledger import links, titles


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Saint Sword (Japan)", "saintsword"),
        ("Saint Sword", "saintsword"),
        ("Pok\u00e9mon: Red (USA) (Rev 1)", "pokemonred"),
        ("SAME! Same! Same!", "samesamesame"),
    ],
)
def test_normalize(title: str, expected: str) -> None:
    assert titles.normalize(title) == expected


@pytest.mark.parametrize(
    ("game", "expected"),
    [
        ("Alpha (USA) (Rev 1)", "usa"),
        ("Alpha (USA, Europe)", "usa"),
        ("Alpha (World)", "usa"),
        ("Alpha (Japan)", "japan"),
        ("Alpha", None),
    ],
)
def test_region_of(game: str, expected: str | None) -> None:
    assert titles.region_of(game) == expected


def test_region_name_maps_world_to_usa() -> None:
    assert titles.region_name(" World ") == "usa"
    assert titles.region_name("Japan") == "japan"


def test_vimm_search() -> None:
    assert links.vimm_search("NES", "Super Mario Bros. (USA)") == (
        "https://vimm.net/vault/?p=list&system=NES&q=Super+Mario+Bros."
    )


def test_vimm_search_skips_short_titles() -> None:
    assert links.vimm_search("NES", "R (USA)") is None


@pytest.mark.parametrize("hostile", [" " * 50_000, "(" * 50_000, "a" + " (" * 25_000])
def test_normalize_is_linear_on_hostile_input(hostile: str) -> None:
    started = time.monotonic()
    titles.normalize(hostile)
    links.vimm_search("NES", hostile)
    assert time.monotonic() - started < 1


def test_normalize_drops_nested_and_spaced_tags() -> None:
    assert titles.normalize("Alpha   (USA)  (Rev 1)") == "alpha"
