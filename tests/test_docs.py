import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *sorted((ROOT / "docs").glob("*.md"))]
LINK = re.compile(r"\]\(([^)\s]+)\)")


@pytest.mark.parametrize("doc", DOCS, ids=lambda doc: doc.name)
def test_relative_links_resolve(doc: Path) -> None:
    for target in LINK.findall(doc.read_text()):
        if re.match(r"[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
            continue
        assert (doc.parent / target.split("#")[0]).exists(), f"{doc.name}: {target}"


BLOB = "https://github.com/kjiwa/romledger/blob/master/"
RAW = "https://raw.githubusercontent.com/kjiwa/romledger/master/"
ABSOLUTE = re.compile(rf"\]\(({re.escape(BLOB)}|{re.escape(RAW)})([^)\s#]+)")
IMAGE_SRC = re.compile(rf"(?:srcset|src)=\"({re.escape(RAW)})([^\"\s]+)\"")


@pytest.mark.parametrize("doc", DOCS, ids=lambda doc: doc.name)
def test_absolute_links_resolve(doc: Path) -> None:
    text = doc.read_text()
    for _, path in [*ABSOLUTE.findall(text), *IMAGE_SRC.findall(text)]:
        assert (ROOT / path).exists(), f"{doc.name}: {path}"
