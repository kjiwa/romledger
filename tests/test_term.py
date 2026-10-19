import io

import pytest

from romledger import term

HEADER = ("name", "count", "note")
ROWS = [("alpha", "1", "short"), ("b", "200", "a rather long note indeed")]


def test_table_pads_columns_and_right_aligns_numbers() -> None:
    assert term.table(HEADER, ROWS, right={1}) == [
        "name   count  note",
        "alpha      1  short",
        "b        200  a rather long note indeed",
    ]


def test_table_trims_trailing_space() -> None:
    assert all(line == line.rstrip() for line in term.table(HEADER, ROWS))


def test_table_without_a_width_never_truncates() -> None:
    assert term.table(HEADER, ROWS, flex=2)[2].endswith("a rather long note indeed")


def test_table_shrinks_only_the_flex_column_to_fit() -> None:
    lines = term.table(HEADER, ROWS, flex=2, columns=30)
    assert all(len(line) <= 30 for line in lines)
    assert lines == [
        "name   count  note",
        "alpha  1      short",
        "b      200    a rather long n…",
    ]


def test_table_keeps_a_readable_minimum_for_the_flex_column() -> None:
    lines = term.table(HEADER, ROWS, flex=2, columns=5)
    assert lines[2].endswith("a rather lo…")


def test_table_that_already_fits_is_untouched() -> None:
    assert term.table(HEADER, ROWS, flex=2, columns=200) == term.table(HEADER, ROWS, flex=2)


def test_width_is_none_when_not_a_terminal() -> None:
    assert term.width(io.StringIO()) is None


def test_width_reads_the_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setenv("COLUMNS", "97")
    assert term.width(Tty()) == 97
