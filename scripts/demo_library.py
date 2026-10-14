"""Build a fictional library and render the dashboard to PNG files.

Run through scripts/screenshots.sh, which supplies Playwright and romledger.
"""

import os
import random
import socket
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import uvicorn
from playwright.sync_api import Browser, sync_playwright

from romledger import config, state
from romledger.context import load_context
from romledger.web.app import create_app

TOKEN = "demo-token-for-screenshots"
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
VIEWPORTS = {"mobile": (393, 852), "desktop": (1440, 900)}
SCHEMES: tuple[Literal["light", "dark"], ...] = ("light", "dark")
PAGES = {
    "overview": "/",
    "platform": "/platforms/snes",
    "inbox": "/inbox",
    "activity": "/activity",
}
INBOX_FILES = {
    "Atomic Arena (USA).sfc": 1_048_576,
    "Brave Quest (Europe).sfc": 2_097_152,
    "Cosmic Voyage (USA).gb": 262_144,
    "scan-notes.txt": 812,
    "Wild Harbor (USA).nes.part": 524_288,
}
SHOW_DEMO_PATH = """() => document.querySelectorAll("p.path").forEach(
    (element) => { element.textContent = "/mnt/roms/inbox"; })"""
SCAN_LOG = "".join(f"scanning {slug} ...\n" for slug in PLATFORMS) + "scanned 4 platform(s)\n"


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
    for name in ("unmatched", "duplicates"):
        (root / "inbox" / name).mkdir()
    (root / "inbox" / "unmatched" / "mystery.bin").write_bytes(b"\0")
    tables = "".join(f"[platforms.{slug}]\n" for slug in PLATFORMS)
    (root / "config.toml").write_text(
        f'[library]\nroms = "{root / "roms"}"\ninboxes = ["{root / "inbox"}"]\n{tables}'
    )
    os.environ[config.CONFIG_ENV] = str(root / "config.toml")
    os.environ[config.DATA_ENV] = str(root / "data")
    stamp = datetime(2026, 10, 12, 18, 30, tzinfo=UTC).isoformat()
    with state.State(root / "data" / "state.db") as database:
        for slug, count in PLATFORMS.items():
            database.replace_platform(slug, items_for(slug, count), ["/x"] * 3, "demo", stamp)


def serve() -> tuple[uvicorn.Server, str]:
    app = create_app(lambda: load_context(None), TOKEN)
    app.state.services.jobs.start("scan", lambda: print(SCAN_LOG, end="") or True)
    app.state.services.jobs.wait(5)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return server, f"http://127.0.0.1:{port}"


def shoot(browser: Browser, base: str, output: Path) -> list[Path]:
    written = []
    for scheme in SCHEMES:
        for device, (width, height) in VIEWPORTS.items():
            context = browser.new_context(
                viewport={"width": width, "height": height},
                color_scheme=scheme,
            )
            page = context.new_page()
            page.goto(f"{base}/?token={TOKEN}")
            for name, path in PAGES.items():
                page.goto(base + path)
                page.evaluate(SHOW_DEMO_PATH)
                target = output / f"{name}-{device}-{scheme}.png"
                page.screenshot(path=target, full_page=name != "platform")
                written.append(target)
            context.close()
    return written


def main() -> int:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/images")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        build(Path(directory))
        server, base = serve()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            written = shoot(browser, base, output)
            browser.close()
        server.should_exit = True
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
