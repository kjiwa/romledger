import io
import re
import sys

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


class Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize(
    ("env", "tty", "expected"),
    [
        ({}, True, True),
        ({}, False, False),
        ({"NO_COLOR": "1"}, True, False),
        ({"NO_COLOR": "1", "FORCE_COLOR": "1"}, True, False),
        ({"FORCE_COLOR": "1"}, False, True),
        ({"TERM": "dumb"}, True, False),
        ({"NO_COLOR": ""}, True, True),
        ({"FORCE_COLOR": ""}, False, False),
    ],
)
def test_color_follows_no_color_force_color_and_the_terminal(
    env: dict[str, str], tty: bool, expected: bool
) -> None:
    stream = Tty() if tty else io.StringIO()
    assert term.color_enabled(stream, env) is expected


def test_color_defaults_to_the_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert term.color_enabled(Tty()) is False


def test_paint_wraps_only_when_enabled() -> None:
    assert term.paint("ok", "green", True) == "\x1b[32mok\x1b[0m"
    assert term.paint("ok", "green", False) == "ok"
    assert term.paint("", "green", True) == ""


def test_table_paints_the_header_and_chosen_cells_without_moving_columns() -> None:
    def style(column: int, text: str) -> str | None:
        return "green" if column == 1 and text == "1" else None

    plain = term.table(("a", "b"), [("x", "1"), ("y", "22")], right={1})
    painted = term.table(
        ("a", "b"), [("x", "1"), ("y", "22")], right={1}, enabled=True, cell_style=style
    )
    assert painted[0] == "\x1b[1ma\x1b[0m   \x1b[1mb\x1b[0m"
    assert painted[1] == "x   \x1b[32m1\x1b[0m"
    assert painted[2] == plain[2]
    assert [re.sub(r"\x1b\[[0-9;]*m", "", line) for line in painted] == plain


def test_a_table_without_a_cell_style_only_paints_the_header() -> None:
    lines = term.table(("a",), [("x",)], enabled=True)
    assert lines == ["\x1b[1ma\x1b[0m", "x"]


def test_say_colors_the_leading_verb_only_on_a_color_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    out = io.StringIO()
    for line in (
        "moved nes 2",
        "not found Game (USA)",
        "failed x: boom",
        "inbox is empty",
        "moved",
    ):
        term.say(line, out)
    assert out.getvalue().splitlines() == [
        "\x1b[32mmoved\x1b[0m nes 2",
        "\x1b[33mnot found\x1b[0m Game (USA)",
        "\x1b[31mfailed\x1b[0m x: boom",
        "inbox is empty",
        "\x1b[32mmoved\x1b[0m",
    ]


def test_say_prints_plain_lines_when_piped(capsys: pytest.CaptureFixture[str]) -> None:
    term.say("moved nes 2")
    assert capsys.readouterr().out == "moved nes 2\n"


def test_error_and_warning_name_the_program_and_go_to_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    term.error("it broke")
    term.warning("be careful")
    term.note("fyi")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "romledger: error: it broke\nromledger: warning: be careful\nfyi\n"


def test_error_label_is_colored_on_a_color_terminal(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    term.error("it broke")
    term.warning("be careful")
    assert capsys.readouterr().err == (
        "romledger: \x1b[31merror:\x1b[0m it broke\nromledger: \x1b[33mwarning:\x1b[0m be careful\n"
    )


def test_progress_is_silent_unless_stderr_is_a_terminal(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    term.progress("working ...")
    assert capsys.readouterr().err == ""
    monkeypatch.setattr(term, "stderr_is_tty", lambda: True)
    term.progress("working ...")
    assert capsys.readouterr().err == "working ...\n"


def test_the_real_tty_check_reads_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stderr", Tty())
    assert term.stderr_is_tty() is True
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    assert term.stderr_is_tty() is False
