"""Write a fictional library, its config.toml and scan results into an empty directory.

Used by scripts/demo.sh and scripts/extension_check.py.
"""

import os
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

from romledger import config, state

ADJECTIVES = [
    "Atomic",
    "Brave",
    "Cosmic",
    "Crimson",
    "Electric",
    "Frozen",
    "Golden",
    "Hidden",
    "Iron",
    "Jade",
    "Lunar",
    "Neon",
    "Obsidian",
    "Phantom",
    "Quantum",
    "Rapid",
    "Silent",
    "Turbo",
    "Velvet",
    "Wild",
]
NOUNS = [
    "Arena",
    "Blaster",
    "Caverns",
    "Drifter",
    "Empire",
    "Fortress",
    "Garden",
    "Harbor",
    "Island",
    "Jungle",
    "Knights",
    "Labyrinth",
    "Mission",
    "Odyssey",
    "Pilot",
    "Quest",
    "Raiders",
    "Summit",
    "Temple",
    "Voyage",
]
REGIONS = ("(USA)", "(USA)", "(USA)", "(Europe)", "(World)")
PLATFORMS = {"nes": 260, "snes": 180, "genesis": 120, "gb": 90}
HAVE_SHARE = {"nes": 0.74, "snes": 0.52, "genesis": 0.31, "gb": 0.9}
INBOX_FILES = {
    "Atomic Arena (USA).sfc": 1_048_576,
    "Brave Quest (Europe).sfc": 2_097_152,
    "Cosmic Voyage (USA).gb": 262_144,
    "scan-notes.txt": 812,
    "Wild Harbor (USA).nes.part": 524_288,
}


def titles(slug: str, count: int) -> list[str]:
    rng = random.Random(slug)
    stems = [f"{a} {n}" for a in ADJECTIVES for n in NOUNS]
    rng.shuffle(stems)
    return [f"{stem} {rng.choice(REGIONS)}" for stem in stems[:count]]


def items_for(slug: str, count: int) -> list[state.Item]:
    rng = random.Random(slug + "-state")
    items = []
    for name in sorted(set(titles(slug, count))):
        roll = rng.random()
        if roll < HAVE_SHARE[slug]:
            items.append(state.Item(name, "have", f"/library/{slug}/{name}.rom"))
        elif roll > 0.99:
            items.append(state.Item(name, "inbox", f"/inbox/{name}.rom"))
        else:
            items.append(state.Item(name, "missing", None))
    return items


def build(root: Path) -> None:
    for name in ("roms", "inbox", "data"):
        (root / name).mkdir()
    for name, size in INBOX_FILES.items():
        (root / "inbox" / name).write_bytes(b"\0" * size)
    for name in ("unmatched", "unwanted", "duplicates"):
        (root / "inbox" / name).mkdir()
    (root / "inbox" / "unmatched" / "mystery.bin").write_bytes(b"\0")
    (root / "inbox" / "unwanted" / "Neon Raiders (Japan).sfc").write_bytes(b"\0")
    (root / "config.toml").write_text(
        f'[library]\nroms = "{root / "roms"}"\ninboxes = ["{root / "inbox"}"]\n'
    )
    os.environ[config.CONFIG_ENV] = str(root / "config.toml")
    os.environ[config.DATA_ENV] = str(root / "data")
    stamp = datetime(2026, 10, 12, 18, 30, tzinfo=UTC).isoformat()
    with state.State(root / "data" / "state.db") as database:
        for slug, count in PLATFORMS.items():
            database.replace_platform(slug, items_for(slug, count), ["/x"] * 3, "demo", stamp)


def write_library(directory: Path) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    build(directory)
    return 0


def main() -> int:
    if sys.argv[1:2] != ["--library"] or len(sys.argv) != 3:
        print("usage: demo_library.py --library DIR", file=sys.stderr)
        return 2
    return write_library(Path(sys.argv[2]))


if __name__ == "__main__":
    sys.exit(main())
