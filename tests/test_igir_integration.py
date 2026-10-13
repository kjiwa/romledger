import hashlib
import shutil
import zlib
from pathlib import Path

import pytest

from rom_scraper import igir
from rom_scraper.igir import ReportRow

pytestmark = pytest.mark.igir

GAMES = {
    "Alpha (USA)": b"A" * 1000,
    "Alpha (Europe)": b"B" * 1100,
    "Beta (USA)": b"C" * 1200,
    "Gamma (Japan)": b"D" * 1300,
}


def dat_text() -> str:
    games = "".join(
        f'game (\n\tname "{name}"\n\tdescription "{name}"\n'
        f'\trom ( name "{name}.nes" size {len(data)} crc {zlib.crc32(data):08x} '
        f"md5 {hashlib.md5(data).hexdigest()} "  # noqa: S324
        f"sha1 {hashlib.sha1(data).hexdigest()} )\n)\n"  # noqa: S324
        for name, data in GAMES.items()
    )
    return f'clrmamepro (\n\tname "Test"\n\tversion "2026.10.01"\n)\n{games}'


@pytest.mark.skipif(
    not (shutil.which("igir") or shutil.which("npx")), reason="igir or npx is required"
)
def test_report_statuses(tmp_path: Path) -> None:
    dat = tmp_path / "test.dat"
    dat.write_text(dat_text())
    library = tmp_path / "library"
    library.mkdir()
    for name in ("Alpha (USA)", "Beta (USA)"):
        (library / f"{name}.nes").write_bytes(GAMES[name])
    (library / "Mystery.nes").write_bytes(b"?" * 500)

    rows = igir.report(dat, [library], ("USA",), ("EN",), tmp_path / "cache" / "igir.cache")

    statuses = {(row.status, row.game) for row in rows if row.game}
    assert statuses == {("FOUND", "Alpha (USA)"), ("FOUND", "Beta (USA)")}
    unused = [row for row in rows if row.status == "UNUSED"]
    assert [Path(row.path).name for row in unused] == ["Mystery.nes"]
    assert all(isinstance(row, ReportRow) for row in rows)
