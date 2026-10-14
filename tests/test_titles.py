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


def test_vimm_search() -> None:
    assert links.vimm_search("NES", "Super Mario Bros. (USA)") == (
        "https://vimm.net/vault/?p=list&system=NES&q=Super+Mario+Bros."
    )


def test_vimm_search_skips_short_titles() -> None:
    assert links.vimm_search("NES", "R (USA)") is None


def test_archive_search_drops_tags() -> None:
    assert links.archive_search("Super Mario Bros. (USA)") == (
        "https://archive.org/search?query=Super+Mario+Bros."
    )


def test_archive_search_keeps_a_name_that_is_only_tags() -> None:
    assert links.archive_search("(USA)") == "https://archive.org/search?query=%28USA%29"
