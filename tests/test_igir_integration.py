import hashlib
import shutil
import zipfile
import zlib
from pathlib import Path

import pytest

from romledger import cli, config, igir, registry
from romledger.igir import ReportRow

pytestmark = pytest.mark.igir

GAMES = {
    "Alpha (USA)": b"A" * 1000,
    "Alpha (Europe)": b"B" * 1100,
    "Beta (USA)": b"C" * 1200,
    "Gamma (Japan)": b"D" * 1300,
}


@pytest.fixture(autouse=True)
def only_nes(monkeypatch: pytest.MonkeyPatch) -> None:
    nes = registry.load()["nes"]
    monkeypatch.setattr(registry, "load", lambda: {"nes": nes})


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
    )

    statuses = {(row.status, row.game) for row in rows if row.game}
    assert statuses == {
        ("FOUND", "Alpha (USA)"),
        ("FOUND", "Beta (USA)"),
        ("MISSING", "Alpha (Europe)"),
        ("MISSING", "Gamma (Japan)"),
    }
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
    (inbox / "Gamma (Japan).nes").write_bytes(GAMES["Gamma (Japan)"])
    junk = {"._junk": b"j", ".DS_Store": b"d", "x.part": b"p"}
    for name, content in junk.items():
        (inbox / name).write_bytes(content)
    path = tmp_path / "config.toml"
    path.write_text(f'[library]\nroms = "{roms}"\ninboxes = ["{inbox}"]\n')

    assert cli.main(["--config", str(path), "import"]) == 0
    assert capsys.readouterr().out == (
        "moved nes 1\n"
        "duplicates 1 (moved to <inbox>/duplicates)\n"
        "unwanted 1 (moved to <inbox>/unwanted)\n"
        "unmatched 1 (moved to <inbox>/unmatched)\n"
    )
    assert names(roms / "nes") == {"Alpha (USA).nes", "Beta (USA).nes"}
    assert names(inbox) == {
        "duplicates/Alpha (USA).nes",
        "unwanted/Gamma (Japan).nes",
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


@needs_igir
@pytest.mark.parametrize("inner", ["Alpha (USA).nes", "alpha.nes"])
def test_import_extracts_a_zip_with_an_extra_file_and_keeps_the_inbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], inner: str
) -> None:
    data = tmp_path / "data"
    monkeypatch.setenv(config.DATA_ENV, str(data))
    dat = data / "dats" / "no-intro" / f"{NES}.dat"
    dat.parent.mkdir(parents=True)
    dat.write_text(dat_text(NES))
    roms, inbox = tmp_path / "roms", tmp_path / "inbox"
    roms.mkdir()
    inbox.mkdir()
    with zipfile.ZipFile(inbox / "download.zip", "w") as archive:
        archive.writestr(inner, GAMES["Alpha (USA)"])
        archive.writestr("readme.txt", "downloaded from somewhere")
    path = tmp_path / "config.toml"
    path.write_text(f'[library]\nroms = "{roms}"\ninboxes = ["{inbox}"]\n')

    assert cli.main(["--config", str(path), "import"]) == 0
    assert capsys.readouterr().out == ("moved nes 1\nextracted 1 (moved to <inbox>/extracted)\n")
    assert names(roms / "nes") == {"Alpha (USA).nes"}
    assert names(inbox) == {"extracted/download.zip"}
    assert cli.main(["--config", str(path), "import"]) == 0
    assert capsys.readouterr().out == "inbox is empty\n"
    assert cli.main(["--config", str(path), "status"]) == 0
    assert capsys.readouterr().out.splitlines()[1].split()[:3] == ["nes", "2", "1"]


@needs_igir
def test_import_survives_the_inbox_being_removed_under_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    monkeypatch.setenv(config.DATA_ENV, str(data))
    dat = data / "dats" / "no-intro" / f"{NES}.dat"
    dat.parent.mkdir(parents=True)
    dat.write_text(dat_text(NES))
    roms, inbox = tmp_path / "roms", tmp_path / "inbox"
    roms.mkdir()
    inbox.mkdir()
    (inbox / "Alpha (USA).nes").write_bytes(GAMES["Alpha (USA)"])
    path = tmp_path / "config.toml"
    path.write_text(f'[library]\nroms = "{roms}"\ninboxes = ["{inbox}"]\n')
    monkeypatch.chdir(inbox)

    assert cli.main(["--config", str(path), "import"]) == 0
    assert "moved nes 1" in capsys.readouterr().out
    with pytest.raises(FileNotFoundError):
        Path.cwd()
    assert cli.main(["--config", str(path), "status"]) == 0
    assert capsys.readouterr().out.splitlines()[1].split()[:3] == ["nes", "2", "1"]


@needs_igir
def test_import_files_a_game_whose_name_repeats_in_another_dat_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    primary, alternate = b"P" * 1000, b"Q" * 1000
    data = tmp_path / "data"
    monkeypatch.setenv(config.DATA_ENV, str(data))
    dat = data / "dats" / "no-intro" / f"{NES}.dat"
    dat.parent.mkdir(parents=True)
    blocks = "".join(
        f'game (\n\tname "Delta (USA)"\n\trom ( name "{name}" size {len(content)} '
        f"crc {zlib.crc32(content):08x} )\n)\n"
        for name, content in (("Delta (USA).nes", primary), ("Delta (USA) (Alt).nes", alternate))
    )
    dat.write_text(f'clrmamepro (\n\tname "{NES}"\n\tversion "2026.10.01"\n)\n{blocks}')
    roms, inbox = tmp_path / "roms", tmp_path / "inbox"
    roms.mkdir()
    inbox.mkdir()
    (inbox / "Delta (USA).nes").write_bytes(alternate)
    path = tmp_path / "config.toml"
    path.write_text(f'[library]\nroms = "{roms}"\ninboxes = ["{inbox}"]\n')

    assert cli.main(["--config", str(path), "import"]) == 0
    assert capsys.readouterr().out == "moved nes 1\n"
    assert names(roms / "nes") == {"Delta (USA) (Alt).nes"}
    assert names(inbox) == set()
