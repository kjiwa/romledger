from pathlib import Path

from romledger import datindex, lookup, state

SHA = "a" * 40
DAT = f"""clrmamepro (
\tversion "1"
)
game (
\tname "Alpha (USA)"
\trom ( name "a.nes" size 1 sha1 {SHA} )
)
game (
\tname "Alpha (Europe)"
\trom ( name "a2.nes" size 1 sha1 {"b" * 40} )
)
game (
\tname "Cat (USA)"
\trom ( name "c.nes" size 1 sha1 {"c" * 40} )
)
game (
\tname "Dog (Japan)"
\trom ( name "d.nes" size 1 sha1 {"d" * 40} )
)
game (
\tname "Dog (USA)"
\trom ( name "d2.nes" size 1 sha1 {"e" * 40} )
)
game (
\tname "Dog (USA) (Rev 1)"
\trom ( name "d3.nes" size 1 sha1 {"f" * 40} )
)
game (
\tname "Mix (USA)"
\trom ( name "m.nes" size 1 sha1 {"1" * 40} )
)
game (
\tname "Mix (USA) (Rev 1)"
\trom ( name "m2.nes" size 1 sha1 {"2" * 40} )
)
game (
\tname "Ten (USA, Europe)"
\trom ( name "t1.nes" size 1 sha1 {"4" * 40} )
)
game (
\tname "Ten (Japan)"
\trom ( name "t2.nes" size 1 sha1 {"5" * 40} )
)
game (
\tname "Ten (USA) (Retro-Bit Generations)"
\trom ( name "t3.nes" size 1 sha1 {"6" * 40} )
)
game (
\tname "Fox (Japan)"
\trom ( name "f.nes" size 1 sha1 {"3" * 40} )
)
"""


def build(tmp_path: Path, *, scanned: bool = True) -> state.State:
    dat = tmp_path / "t.dat"
    dat.write_text(DAT)
    database = state.State(tmp_path / "state.db")
    datindex.ensure(database, "nes", dat)
    if scanned:
        items = [
            state.Item("Alpha (USA)", "have", "/a"),
            state.Item("Cat (USA)", "missing", None),
            state.Item("Mix (USA)", "missing", None),
        ]
        database.replace_platform("nes", items, [], "1", "t")
    return database


def test_hash_match_reports_state_case_insensitively(tmp_path: Path) -> None:
    with build(tmp_path) as database:
        assert lookup.by_hash(database, SHA.upper()) == [
            lookup.Match("nes", "Alpha (USA)", lookup.HAVE, True)
        ]
        assert lookup.by_hash(database, "c" * 40)[0].state == lookup.MISSING
        assert lookup.by_hash(database, "d" * 40)[0].state == lookup.UNWANTED


def test_unknown_hash(tmp_path: Path) -> None:
    with build(tmp_path) as database:
        assert lookup.by_hash(database, "9" * 40) == [lookup.Match(None, None, "unknown", True)]


def test_unscanned_platform(tmp_path: Path) -> None:
    with build(tmp_path, scanned=False) as database:
        assert lookup.by_hash(database, SHA)[0].state == lookup.UNSCANNED


def test_exact_name(tmp_path: Path) -> None:
    with build(tmp_path) as database:
        assert lookup.by_name(database, "nes", "Cat (USA)") == [
            lookup.Match("nes", "Cat (USA)", lookup.MISSING, True)
        ]


def test_name_without_candidates_is_unknown(tmp_path: Path) -> None:
    with build(tmp_path) as database:
        assert lookup.by_name(database, "nes", "Zed") == [
            lookup.Match("nes", "Zed", lookup.UNKNOWN, False)
        ]


def test_title_match_is_approximate_and_prefers_the_region(tmp_path: Path) -> None:
    with build(tmp_path) as database:
        assert lookup.by_name(database, "nes", "alpha (europe) (rev a)") == [
            lookup.Match("nes", "Alpha (Europe)", lookup.UNWANTED, False)
        ]
        assert lookup.by_name(database, "nes", "Cat") == [
            lookup.Match("nes", "Cat (USA)", lookup.MISSING, False)
        ]


def test_region_without_a_candidate_falls_back_to_all(tmp_path: Path) -> None:
    with build(tmp_path) as database:
        assert lookup.by_name(database, "nes", "Fox (USA)") == [
            lookup.Match("nes", "Fox (Japan)", lookup.UNWANTED, False)
        ]


def test_ambiguous_title_returns_every_candidate_unless_one_is_wanted(tmp_path: Path) -> None:
    with build(tmp_path) as database:
        assert lookup.by_name(database, "nes", "Dog (USA) (Beta)") == [
            lookup.Match("nes", "Dog (USA)", lookup.UNWANTED, False),
            lookup.Match("nes", "Dog (USA) (Rev 1)", lookup.UNWANTED, False),
        ]
        assert lookup.by_name(database, "nes", "Mix (USA) (Beta)") == [
            lookup.Match("nes", "Mix (USA)", lookup.MISSING, False)
        ]


def games(matches: list[lookup.Match]) -> list[str | None]:
    return [match.game for match in matches]


def test_regions_narrow_a_bare_title(tmp_path: Path) -> None:
    with build(tmp_path) as database:
        assert games(lookup.by_name(database, "nes", "Ten", ("USA", "Europe"))) == [
            "Ten (USA) (Retro-Bit Generations)",
            "Ten (USA, Europe)",
        ]
        assert games(lookup.by_name(database, "nes", "Ten", ("Japan",))) == ["Ten (Japan)"]
        assert games(lookup.by_name(database, "nes", "Ten", ("World",))) == [
            "Ten (USA) (Retro-Bit Generations)",
            "Ten (USA, Europe)",
        ]


def test_extra_title_tags_narrow_further(tmp_path: Path) -> None:
    with build(tmp_path) as database:
        assert games(lookup.by_name(database, "nes", "Ten (Retro-Bit Generations)", ("USA",))) == [
            "Ten (USA) (Retro-Bit Generations)"
        ]


def test_unmatched_regions_fall_back_to_every_candidate(tmp_path: Path) -> None:
    with build(tmp_path) as database:
        assert len(lookup.by_name(database, "nes", "Ten", ("Brazil",))) == 3


def test_title_with_no_ascii_never_fuzzy_matches(tmp_path: Path) -> None:
    with build(tmp_path) as database:
        database.replace_index(
            "nes",
            [],
            [state.IndexedGame("\u30b2\u30fc\u30e0 (Japan)", "", "japan")],
            state.DatStamp("1", 0, 0),
        )
        assert lookup.by_name(database, "nes", "\u3042\u3044 (Japan)") == [
            lookup.Match("nes", "\u3042\u3044 (Japan)", lookup.UNKNOWN, False)
        ]
