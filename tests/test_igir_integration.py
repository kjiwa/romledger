import hashlib
import shutil
import zlib
from pathlib import Path

import pytest

from romledger import cli, config, igir
from romledger.igir import ReportRow

pytestmark = pytest.mark.igir

GAMES = {
    "Alpha (USA)": b"A" * 1000,
    "Alpha (Europe)": b"B" * 1100,
    "Beta (USA)": b"C" * 1200,
    "Gamma (Japan)": b"D" * 1300,
}


def dat_text(name: str = "Test") -> str:
    games = "".join(
        f'game (\n\tname "{name}"\n\tdescription "{name}"\n'
        f'\trom ( name "{name}.nes" size {len(data)} crc {zlib.crc32(data):08x} '
        f"md5 {hashlib.md5(data).hexdigest()} "  # noqa: S324
        f"sha1 {hashlib.sha1(data).hexdigest()} )\n)\n"  # noqa: S324
        for name, data in GAMES.items()
    )
    return f'clrmamepro (\n\tname "{name}"\n\tversion "2026.10.01"\n)\n{games}'


needs_igir = pytest.mark.skipif(
    not (shutil.which("igir") or shutil.which("npx")), reason="igir or npx is required"
)


@needs_igir
def test_report_statuses(tmp_path: Path) -> None:
    dat = tmp_path / "test.dat"
    dat.write_text(dat_text())
    library = tmp_path / "library"
    library.mkdir()
    for name in ("Alpha (USA)", "Beta (USA)"):
        (library / f"{name}.nes").write_bytes(GAMES[name])
    (library / "Mystery.nes").write_bytes(b"?" * 500)

    rows = igir.report(
        [dat],
        [library],
        tmp_path / "cache" / "igir.cache",
        igir.Filters(("USA",), ("EN",)),
    )

    statuses = {(row.status, row.game) for row in rows if row.game}
    assert statuses == {("FOUND", "Alpha (USA)"), ("FOUND", "Beta (USA)")}
    unused = [row for row in rows if row.status == "UNUSED"]
    assert [Path(row.path).name for row in unused] == ["Mystery.nes"]
    assert all(isinstance(row, ReportRow) for row in rows)


NES = "Nintendo - Nintendo Entertainment System"


def names(directory: Path) -> set[str]:
    return {str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file()}


@needs_igir
def test_import_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    monkeypatch.setenv(config.DATA_ENV, str(data))
    dat = data / "dats" / "no-intro" / f"{NES}.dat"
    dat.parent.mkdir(parents=True)
    dat.write_text(dat_text(NES))
    roms, inbox = tmp_path / "roms", tmp_path / "inbox"
    (roms / "nes").mkdir(parents=True)
    (inbox / "sub").mkdir(parents=True)
    (roms / "nes" / "Alpha (USA).nes").write_bytes(GAMES["Alpha (USA)"])
    (inbox / "Alpha (USA).nes").write_bytes(GAMES["Alpha (USA)"])
    (inbox / "sub" / "Beta (USA).nes").write_bytes(GAMES["Beta (USA)"])
    (inbox / "Mystery.nes").write_bytes(b"?" * 500)
    junk = {"._junk": b"j", ".DS_Store": b"d", "x.part": b"p"}
    for name, content in junk.items():
        (inbox / name).write_bytes(content)
    path = tmp_path / "config.toml"
    path.write_text(
        f'[library]\nroms = "{roms}"\ninboxes = ["{inbox}"]\n'
        f'[platforms.nes]\ndat = "no-intro/{NES}"\n'
    )

    assert cli.main(["--config", str(path), "import"]) == 0
    assert capsys.readouterr().out == (
        "moved nes 1\n"
        "duplicates 1 (moved to <inbox>/duplicates)\n"
        "unmatched 1 (moved to <inbox>/unmatched)\n"
    )
    assert names(roms / "nes") == {"Alpha (USA).nes", "Beta (USA).nes"}
    assert names(inbox) == {
        "duplicates/Alpha (USA).nes",
        "unmatched/Mystery.nes",
        *junk,
    }

    assert cli.main(["--config", str(path), "import"]) == 0
    assert capsys.readouterr().out == "inbox is empty\n"

    (roms / "nes" / "Beta (USA).nes").rename(inbox / "unmatched" / "Beta (USA).nes")
    assert cli.main(["--config", str(path), "scan"]) == 0
    capsys.readouterr()
    assert cli.main(["--config", str(path), "status"]) == 0
    status = capsys.readouterr().out.splitlines()[1].split()
    assert status[:6] == ["nes", "2", "1", "0", "1", "0"]
