import time

import pytest

from romledger import catalog
from romledger.catalog import Game

USA, WORLD, EN = ("USA",), ("USA", "WORLD"), ("EN",)


def game(name: str, *rom_names: str) -> Game:
    return Game(name, rom_names or (f"{name}.nes",))


def wanted(
    games: list[Game],
    regions: tuple[str, ...] = WORLD,
    languages: tuple[str, ...] = EN,
    include: tuple[str, ...] = (),
) -> list[tuple[str, ...]]:
    return [group.members for group in catalog.wanted_groups(games, regions, languages, include)]


@pytest.mark.parametrize(
    "name",
    [
        "Alpha (USA) (Unl)",
        "Alpha (USA) (Pirate)",
        "Alpha (USA) (Aftermarket)",
        "Alpha (USA) (Homebrew)",
        "Alpha (USA) (Proto)",
        "Alpha (USA) (Beta 2)",
        "Alpha (USA) (Demo)",
        "Alpha (USA) (Sample)",
        "Alpha (USA) (Kiosk)",
        "Alpha (USA) (Debug)",
        "Alpha (USA) (Program)",
        "Alpha (USA) (Test Program)",
        "Alpha (USA) [b]",
        "Alpha (USA) [b2]",
        "Alpha (USA) (Possible Proto)",
        "Alpha (USA) (Auto Demo)",
        "Alpha (World) (Tech Demo)",
        "Alpha (Japan) (Jitsuen-you Sample)",
        "Alpha (USA) (Movie Demo Disc)",
        "Alpha (USA) (Music Program)",
        "Alpha (USA) (Ending Credits Program)",
        "Alpha (USA) (Enhancement Chip)",
        "Alpha (USA) (Kiosk, GameCube)",
        "Alpha (USA) (En,Fr) (Possible Proto)",
    ],
)
def test_excluded_by_game_name_tag(name: str) -> None:
    assert wanted([game(name)]) == []


def test_excluded_by_rom_name_tag_when_the_game_name_is_clean() -> None:
    assert wanted([game("Alpha (USA)", "Alpha (USA) (Aftermarket) (Unl).nes")]) == []


def test_tags_must_match_whole_words() -> None:
    games = [game("Alpha (USA) (Unlimited)"), game("Beta (USA) (Betamax)")]
    games.append(game("Gamma (USA) (Riff Sampler Test)"))
    assert wanted(games) == [
        ("Alpha (USA) (Unlimited)",),
        ("Beta (USA) (Betamax)",),
        ("Gamma (USA) (Riff Sampler Test)",),
    ]


def test_bad_dump_flag_matches_only_a_leading_b() -> None:
    assert wanted([game("Alpha (USA) (Fan b)")]) == [("Alpha (USA) (Fan b)",)]


def test_official_distribution_tags_are_kept() -> None:
    names = ["A (USA) (Sega Channel)", "B (USA) (Virtual Console)", "C (USA) (Competition Cart)"]
    assert len(wanted([game(name) for name in names])) == 3


def test_include_keeps_a_category() -> None:
    games = [game("Alpha (USA)"), game("Alpha (USA) (Unl)"), game("Beta (USA) (Proto)")]
    assert wanted(games, include=("unlicensed",)) == [("Alpha (USA)", "Alpha (USA) (Unl)")]
    assert wanted(games, include=("unlicensed", "prerelease")) == [
        ("Alpha (USA)", "Alpha (USA) (Unl)"),
        ("Beta (USA) (Proto)",),
    ]


def test_every_category_is_includable() -> None:
    names = ["A (USA) (Unl)", "B (USA) (Homebrew)", "C (USA) (Demo)", "D (USA) (Program)"]
    names.append("E (USA) [b]")
    games = [game(name) for name in names]
    assert len(wanted(games, include=catalog.CATEGORIES)) == 5


def test_region_and_language_filter() -> None:
    games = [
        game("Alpha (Japan)"),
        game("Beta (Europe) (En,Fr)"),
        game("Cat (Japan, USA) (En)"),
        game("Dog (Europe) (Fr,De)"),
        game("Eel (World)"),
        game("Fox (Japan) (En)"),
        game("Gnu (Sweden)"),
        game("Hen (Unknown)"),
    ]
    assert wanted(games) == [("Cat (Japan, USA) (En)",), ("Eel (World)",)]
    assert wanted(games, regions=("EUR",)) == [("Beta (Europe) (En,Fr)",)]
    assert wanted(games, regions=("EUR",), languages=("FR",)) == [
        ("Beta (Europe) (En,Fr)",),
        ("Dog (Europe) (Fr,De)",),
    ]
    assert wanted(games, regions=("JPN",), languages=("JA",)) == [("Alpha (Japan)",)]


def test_language_is_implied_by_region_when_untagged() -> None:
    games = [game("Alpha (France)"), game("Beta (Germany) (En)"), game("Cat (Netherlands)")]
    assert wanted(games, regions=("FRA", "GER", "HOL"), languages=("FR",)) == [("Alpha (France)",)]
    assert wanted(games, regions=("FRA", "GER", "HOL"), languages=("EN",)) == [
        ("Beta (Germany) (En)",)
    ]
    assert wanted(games, regions=("HOL",), languages=("NL",)) == [("Cat (Netherlands)",)]


def test_game_without_a_region_is_not_wanted() -> None:
    assert wanted([game("Alpha")]) == []


def test_groups_share_a_base_title_and_sort_by_title() -> None:
    games = [game("Zed (USA)"), game("Alpha (USA) (Rev 1)"), game("Alpha (USA)")]
    assert wanted(games) == [("Alpha (USA) (Rev 1)", "Alpha (USA)"), ("Zed (USA)",)]


def test_preferred_has_no_extra_tags() -> None:
    games = [
        game("Alpha (USA) (Evercade)"),
        game("Alpha (USA) (Virtual Console) (Rev 3)"),
        game("Alpha (USA)"),
    ]
    assert wanted(games)[0][0] == "Alpha (USA)"


def test_preferred_follows_region_order() -> None:
    games = [game("Alpha (World)"), game("Alpha (USA)")]
    assert wanted(games, regions=("USA", "WORLD"))[0][0] == "Alpha (USA)"
    assert wanted(games, regions=("WORLD", "USA"))[0][0] == "Alpha (World)"


def test_preferred_follows_the_best_region_of_a_multi_region_game() -> None:
    games = [game("Alpha (Europe)"), game("Alpha (Japan, USA) (En)")]
    assert wanted(games, regions=("USA", "EUR"))[0][0] == "Alpha (Japan, USA) (En)"


def test_preferred_follows_language_order() -> None:
    games = [game("Alpha (Europe) (Fr,De)"), game("Alpha (Europe) (En,De)")]
    assert wanted(games, regions=("EUR",), languages=("FR", "EN"))[0][0] == (
        "Alpha (Europe) (Fr,De)"
    )
    assert wanted(games, regions=("EUR",), languages=("EN", "FR"))[0][0] == (
        "Alpha (Europe) (En,De)"
    )


@pytest.mark.parametrize(
    ("older", "newer"),
    [
        ("Alpha (USA)", "Alpha (USA) (Rev 1)"),
        ("Alpha (USA) (Rev 1)", "Alpha (USA) (Rev 2)"),
        ("Alpha (USA) (Rev A)", "Alpha (USA) (Rev B)"),
        ("Alpha (USA) (v1.0)", "Alpha (USA) (v1.1)"),
        ("Alpha (USA) (v1.9)", "Alpha (USA) (v1.10)"),
    ],
)
def test_preferred_is_the_newest_revision(older: str, newer: str) -> None:
    assert wanted([game(older), game(newer)])[0][0] == newer
    assert wanted([game(newer), game(older)])[0][0] == newer


def test_members_are_ordered_best_first() -> None:
    games = [game("Alpha (World)"), game("Alpha (USA) (Rev 1)"), game("Alpha (USA)")]
    assert wanted(games) == [("Alpha (USA) (Rev 1)", "Alpha (USA)", "Alpha (World)")]


def test_tag_scanning_is_linear() -> None:
    started = time.monotonic()
    wanted([game("(" * 50000 + "A (USA)"), game("A" + " " * 50000 + "(USA)")])
    assert time.monotonic() - started < 1


def test_each_disc_is_its_own_group() -> None:
    games = [
        game("Game (USA) (Disc 2)"),
        game("Game (USA) (Disc 1)"),
        game("Game (USA) (Disc 1) (Rev 1)"),
        game("Game (USA) (Track 1)"),
        game("Game (USA) (Side A)"),
        game("Game (USA) (Part 1)"),
    ]
    assert wanted(games) == [
        ("Game (USA) (Disc 1) (Rev 1)", "Game (USA) (Disc 1)"),
        ("Game (USA) (Disc 2)",),
        ("Game (USA) (Part 1)",),
        ("Game (USA) (Side A)",),
        ("Game (USA) (Track 1)",),
    ]


def test_disc_tags_do_not_count_as_extras() -> None:
    games = [game("Game (USA) (Disc 1) (Evercade)"), game("Game (USA) (Disc 1)")]
    assert wanted(games) == [("Game (USA) (Disc 1)", "Game (USA) (Disc 1) (Evercade)")]


def test_titles_without_ascii_do_not_collapse() -> None:
    games = [game("\u30b2\u30fc\u30e0 (Japan)"), game("\u30c9\u30e9\u30b4\u30f3 (Japan)")]
    groups = wanted(games, regions=("JPN",), languages=("JA",))
    assert sorted(groups) == sorted([(games[0].name,), (games[1].name,)])
    twin = game("\u30b2\u30fc\u30e0 (Japan) (Rev 1)")
    assert len(wanted([*games, twin], regions=("JPN",), languages=("JA",))) == 2


@pytest.mark.parametrize(
    ("older", "newer"),
    [
        ("Alpha (USA) (Rev 9)", "Alpha (USA) (Rev 10)"),
        ("Alpha (USA) (v1.9)", "Alpha (USA) (v1.10)"),
        ("Alpha (USA) (Rev 2)", "Alpha (USA) (Rev A)"),
    ],
)
def test_revisions_compare_numerically_and_never_tie(older: str, newer: str) -> None:
    assert wanted([game(older), game(newer)])[0][0] == newer
    assert wanted([game(newer), game(older)])[0][0] == newer


def test_a_better_region_beats_fewer_extra_tags() -> None:
    games = [game("Alpha (Europe)"), game("Alpha (USA) (Virtual Console)")]
    assert wanted(games, regions=("USA", "EUR"))[0][0] == "Alpha (USA) (Virtual Console)"
    assert wanted(games, regions=("EUR", "USA"))[0][0] == "Alpha (Europe)"


def test_a_better_language_beats_fewer_extra_tags() -> None:
    games = [game("Alpha (Europe) (En)"), game("Alpha (Europe) (Fr) (Virtual Console)")]
    assert wanted(games, regions=("EUR",), languages=("FR", "EN"))[0][0] == (
        "Alpha (Europe) (Fr) (Virtual Console)"
    )


# Region names that start a game name in the libretro NES, SNES, Mega Drive, PlayStation and
# Saturn DATs.
DAT_REGIONS = {
    *("Argentina", "Asia", "Australia", "Austria", "Belgium", "Brazil", "Canada", "China"),
    *("Denmark", "Europe", "Finland", "France", "Germany", "Greece", "Hong Kong", "India"),
    *("Ireland", "Israel", "Italy", "Japan", "Korea", "Mexico", "Netherlands", "Norway"),
    *("Peru", "Poland", "Portugal", "Russia", "Scandinavia", "Spain", "Sweden", "Taiwan"),
    *("UK", "United Kingdom", "USA", "Unknown", "World"),
}


def test_every_dat_region_is_mapped_or_knowingly_unconfigurable() -> None:
    unconfigurable = DAT_REGIONS - set(catalog.REGION_CODES)
    assert unconfigurable == {
        "Austria",
        "India",
        "Ireland",
        "Israel",
        "Peru",
        "Poland",
        "Scandinavia",
    }


def test_a_game_with_only_unmapped_regions_is_unwanted() -> None:
    assert wanted([game("Alpha (Poland)"), game("Beta (Poland, USA)")]) == [("Beta (Poland, USA)",)]
