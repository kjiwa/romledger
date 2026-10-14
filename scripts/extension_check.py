"""Load the unpacked extension in Chromium and check it against a fictional library.

Run through scripts/extension-check.sh, which supplies Playwright and romledger. With an output
directory argument it also writes the popup screenshots used by docs/extension.md.
"""

import base64
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

from demo_library import SCHEMES, TOKEN, serve, write_library
from playwright.sync_api import BrowserContext, Page, Route, sync_playwright

from romledger import datindex, dats, state
from romledger.context import load_context

EXTENSION = Path(__file__).resolve().parent.parent / "extension"
SHA1 = {"Alpha Quest (USA)": "a" * 40, "Beta Quest (USA)": "b" * 40, "Gamma Quest (USA)": "c" * 40}
GENESIS = {"Delta Run (USA)": "d" * 40, "Echo Run (USA)": "e" * 40}
ITEM = "gb-item"
MISSING_SHA1 = "f" * 40


def write_dat(path: Path, games: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(
        f'game (\n\tname "{name}"\n\trom ( name "{name}.rom" size 1 sha1 {sha1} )\n)\n'
        for name, sha1 in games.items()
    )
    path.write_text('clrmamepro (\n\tversion "1"\n)\n' + body)


def seed(root: Path) -> None:
    config_file = root / "config.toml"
    config_file.write_text(
        config_file.read_text().replace(
            "[platforms.gb]\n",
            f'[platforms.gb]\nsources = ["internet-archive"]\narchive_item = "{ITEM}"\n',
        )
    )
    context = load_context(None)
    layouts = {
        "gb": (SHA1, ("have", "missing", "inbox")),
        "genesis": (GENESIS, ("have", "missing")),
    }
    with state.State(context.data_dir / "state.db") as database:
        for slug, (games, states) in layouts.items():
            dat = dats.dat_path(context.data_dir, context.config.platforms[slug].dat)
            write_dat(dat, games)
            items = [state.Item(name, kind, None) for name, kind in zip(games, states, strict=True)]
            database.replace_platform(slug, items, [], "1", "2026-10-13T12:00:00+00:00")
            datindex.ensure(database, slug, dat)


def media(name: str, sha1: str) -> dict[str, str]:
    title = base64.b64encode(name.encode()).decode()
    return {"GoodTitle": title, "GoodSha1": sha1.upper(), "Serial": "X"}


def pages() -> dict[tuple[str, str], str]:
    discs = [
        media("Alpha Quest (USA).gb", SHA1["Alpha Quest (USA)"]),
        media("Gamma Quest (USA).gb", MISSING_SHA1),
    ]
    game = (
        "<title>The Vault: Alpha Quest (GB)</title>"
        f"<h2>Alpha Quest</h2><script>allMedia={json.dumps(discs)};</script>"
    )
    rows = "".join(
        f'<tr><td><a href="/vault/{number}">{name}</a></td></tr>'
        for number, name in enumerate(("Alpha Quest", "Beta Quest", "Zeta Quest"), start=10)
    )
    cool = "".join(
        f'<div><a href="/roms/genesis/{number}/{name.replace(" ", "_")}.php">{name}</a></div>'
        for number, name in enumerate(GENESIS, start=1)
    )
    return {
        ("vimm.net", "/vault/77"): game,
        ("vimm.net", "/vault/"): f"<title>GB - The Vault</title><table>{rows}</table>",
        ("coolrom.com", "/roms/genesis/D/"): f"<title>Genesis - D</title>{cool}",
        ("archive.org", f"/details/{ITEM}"): "<title>GB item</title><h1>GB item</h1>",
        ("archive.org", "/details/other"): "<title>Other</title><h1>Other</h1>",
    }


def serve_fixture(route: Route) -> None:
    url = re.match(r"https://([^/]+)(/[^?]*)", route.request.url)
    body = pages().get((url.group(1), url.group(2))) if url else None
    if body is None:
        route.abort()
        return
    route.fulfill(status=200, content_type="text/html", body=f"<!doctype html><body>{body}</body>")


def patched_copy(directory: Path, base: str) -> Path:
    target = directory / "extension"
    shutil.copytree(EXTENSION, target, ignore=shutil.ignore_patterns("test"))
    manifest = json.loads((target / "manifest.json").read_text())
    manifest["host_permissions"] = [f"{base}/*"]
    (target / "manifest.json").write_text(json.dumps(manifest))
    return target


def badges(page: Page, count: int) -> list[str]:
    page.wait_for_function(
        f"document.querySelectorAll('.romledger-badge').length >= {count}", timeout=10000
    )
    return page.eval_on_selector_all(
        ".romledger-badge",
        "(nodes) => nodes.map((node) => node.parentElement.innerText.replace(/\\s+/g, ' ').trim())",
    )


def check_vimm_game(context: BrowserContext) -> list[str]:
    page = context.new_page()
    page.goto("https://vimm.net/vault/77")
    found = badges(page, 2)
    page.close()
    expected = ["Alpha Quest (USA) In library", "Gamma Quest (USA) In inbox"]
    return [] if found == expected else [f"vimm game: {found}"]


def check_vimm_list(context: BrowserContext) -> list[str]:
    page = context.new_page()
    page.goto("https://vimm.net/vault/?p=list&system=GB&q=")
    found = badges(page, 3)
    page.close()
    expected = [
        "Alpha Quest In library (approximate)",
        "Beta Quest Missing (approximate)",
        "Zeta Quest Not in any DAT",
    ]
    return [] if found == expected else [f"vimm list: {found}"]


def check_coolrom(context: BrowserContext) -> list[str]:
    page = context.new_page()
    page.goto("https://coolrom.com/roms/genesis/D/")
    found = badges(page, 2)
    page.close()
    expected = ["Delta Run (USA) In library", "Echo Run (USA) Missing"]
    return [] if found == expected else [f"coolrom: {found}"]


def check_archive(context: BrowserContext) -> list[str]:
    problems = []
    for item, expected in ((ITEM, "of 3 wanted games"), ("other", "Not configured")):
        page = context.new_page()
        page.goto(f"https://archive.org/details/{item}")
        found = badges(page, 1)
        page.close()
        if expected not in found[0]:
            problems.append(f"archive {item}: {found}")
    return problems


def check_popup(context: BrowserContext, extension_id: str, output: Path | None) -> list[str]:
    problems = []
    page = context.new_page()
    page.set_viewport_size({"width": 352, "height": 360})
    for scheme in SCHEMES:
        page.emulate_media(color_scheme=scheme)
        page.goto(f"chrome-extension://{extension_id}/popup.html")
        page.wait_for_selector("#platforms li")
        if page.locator("#platforms li").count() != 4:
            problems.append("popup: expected 4 platforms")
        if output:
            page.screenshot(path=output / f"extension-popup-{scheme}.png")
    page.close()
    return problems


def check_unreachable(context: BrowserContext, extension_id: str, worker: object) -> list[str]:
    worker.evaluate("chrome.storage.local.set({ token: 'wrong' })")  # type: ignore[attr-defined]
    page = context.new_page()
    page.goto("https://vimm.net/vault/?p=list&system=GB&q=")
    found = badges(page, 1)
    page.close()
    return [] if "romledger unavailable" in found[0] else [f"rejected token: {found}"]


def run(base: str, directory: Path, output: Path | None) -> list[str]:
    extension = patched_copy(directory, base)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(directory / "profile"),
            channel="chromium",
            args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"],
        )
        worker = (
            context.service_workers[0]
            if context.service_workers
            else context.wait_for_event("serviceworker")
        )
        extension_id = worker.url.split("/")[2]
        worker.evaluate(f"chrome.storage.local.set({{ url: '{base}', token: '{TOKEN}' }})")
        context.route(
            re.compile(r"https://(vimm\.net|coolrom\.com|archive\.org)/.*"), serve_fixture
        )
        problems = (
            check_vimm_game(context)
            + check_vimm_list(context)
            + check_coolrom(context)
            + check_archive(context)
            + check_popup(context, extension_id, output)
            + check_unreachable(context, extension_id, worker)
        )
        context.close()
    return problems


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write_library(root / "library")
        seed(root / "library")
        server, base = serve()
        problems = run(base, root, output)
        server.should_exit = True
    for problem in problems:
        print(problem)
    print("extension checks: " + ("FAILED" if problems else "ok"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
