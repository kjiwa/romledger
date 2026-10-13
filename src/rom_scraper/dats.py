import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx

BASE_URL = "https://raw.githubusercontent.com/libretro/libretro-database/master/metadat"
VERSION = re.compile(r'^\s*version\s+"([^"]*)"', re.MULTILINE)
NAME = re.compile(r'^\s*name\s+"([^"]*)"', re.MULTILINE)


class DatError(Exception):
    pass


@dataclass(frozen=True)
class Result:
    path: Path
    version: str
    changed: bool


def dat_path(data_dir: Path, dat: str) -> Path:
    return data_dir / "dats" / f"{dat}.dat"


def url(dat: str) -> str:
    return f"{BASE_URL}/{quote(dat)}.dat"


def update(data_dir: Path, dats: Mapping[str, str], client: httpx.Client) -> dict[str, Result]:
    return {slug: _update_one(data_dir, dat, client) for slug, dat in dats.items()}


def version_of(path: Path) -> str:
    match = VERSION.search(path.read_text(encoding="utf-8", errors="replace")[:4096])
    return match.group(1) if match else "unknown"


def name_of(path: Path) -> str:
    match = NAME.search(path.read_text(encoding="utf-8", errors="replace")[:4096])
    return match.group(1) if match else path.stem


def _update_one(data_dir: Path, dat: str, client: httpx.Client) -> Result:
    target = dat_path(data_dir, dat)
    content = _download(url(dat), client)
    changed = not target.is_file() or target.read_bytes() != content
    if changed:
        _write_atomic(target, content)
    return Result(target, version_of(target), changed)


def _download(source: str, client: httpx.Client) -> bytes:
    try:
        response = client.get(source)
    except httpx.HTTPError as error:
        raise DatError(
            f"{source}: request failed ({error}). Check the network and HTTPS_PROXY, then retry."
        ) from error
    if response.status_code != 200:
        raise DatError(
            f"{source}: HTTP {response.status_code}. Check that the dat name exists in "
            "libretro-database, or fix platforms.<slug>.dat."
        )
    return response.content


def _write_atomic(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as temp:
            temp.write(content)
        os.replace(temp_name, target)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
