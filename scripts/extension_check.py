"""Load the unpacked extension in Chromium and check it against a fictional library.

Run through scripts/extension-check.sh, which supplies Playwright and romledger. With an output
directory argument it also writes the popup screenshots used by docs/extension.md.
"""

import base64
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from demo_library import SCHEMES, TOKEN, serve, write_library
from playwright.sync_api import (
    BrowserContext,
    Error,
    Page,
    Playwright,
    Route,
    Worker,
    sync_playwright,
)

from romledger import datindex, dats, state
from romledger.context import load_context

EXTENSION = Path(__file__).resolve().parent.parent / "extension"
SHA1 = {"Alpha Quest (USA)": "a" * 40, "Beta Quest (USA)": "b" * 40, "Gamma Quest (USA)": "c" * 40}
GENESIS = {"Delta Run (USA)": "d" * 40, "Echo Run (USA)": "e" * 40}
QUEUED = {"Foxtrot Run (USA)": "1" * 40, "Golf Run (USA)": "2" * 40}
ITEM = "gb-item"
MISSING_SHA1 = "f" * 40
JAPAN_TWIN = {"gb": {"Omega Quest (Japan)": "9" * 40}}
FLAG = '<img src="/images/flags/{file}.png" class="flag" title="{title}">'


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
        "genesis": ({**GENESIS, **QUEUED}, ("have", "missing", "missing", "missing")),
    }
    with state.State(context.data_dir / "state.db") as database:
        for slug, (games, states) in layouts.items():
            dat = dats.dat_path(context.data_dir, context.config.platforms[slug].dat)
            write_dat(dat, {**games, **JAPAN_TWIN.get(slug, {})})
            items = [state.Item(name, kind, None) for name, kind in zip(games, states, strict=True)]
            database.replace_platform(slug, items, [], "1", "2026-10-13T12:00:00+00:00")
            datindex.ensure(database, slug, dat)


def media(name: str, sha1: str) -> dict[str, str]:
    title = base64.b64encode(name.encode()).decode()
    return {"GoodTitle": title, "GoodSha1": sha1.upper(), "Serial": "X"}


def download_form(number: int) -> str:
    return (
        '<form action="//dl3.vimm.net/" method="POST" id="dl-form">'
        f'<input type="hidden" name="mediaId" value="{number}">'
        '<input type="hidden" name="alt" value="0" disabled>'
        f'<input type="hidden" name="token" value="token{number}"><button>Download</button></form>'
    )


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
        f'<tr><td><a href="/vault/{number}">{name}</a></td><td>{flag}</td></tr>'
        for number, name, flag in (
            (10, "Alpha Quest", ""),
            (11, "Beta Quest", ""),
            (12, "Zeta Quest", ""),
            (13, "Omega Quest", FLAG.format(file="japan", title="Japan")),
        )
    )
    queue_rows = "".join(
        f'<tr><td><a href="/vault/{number}">{name}</a></td></tr>'
        for number, name in ((31, "Foxtrot Run (USA)"), (32, "Golf Run (USA)"), (33, "Echo Run"))
    )
    cool = "".join(
        f'<div><a href="/roms/genesis/{number}/{name.replace(" ", "_")}.php">{name}</a></div>'
        for number, name in enumerate(GENESIS, start=1)
    )
    slugs = {name: name.split(" (")[0].lower().replace(" ", "-") for name in GENESIS}
    console = "".join(
        f'<div><a href="/roms/sega-genesis/{slug}" class="btn" role="button">View</a></div>'
        f'<div><a href="/roms/sega-genesis/{slug}">{name}</a></div>'
        for name, slug in slugs.items()
    )
    emu = "".join(
        f'<div><a href="/en/consoles/genesis/roms/{slug}">{name}</a></div>'
        for name, slug in slugs.items()
    )
    return {
        ("vimm.net", "/vault/77"): game,
        ("vimm.net", "/vault/"): f"<title>GB - The Vault</title><table>{rows}</table>",
        ("vimm.net", "/vault/GB/A"): f"<title>GB - The Vault</title><table>{rows}</table>",
        (
            "vimm.net",
            "/vault/Genesis/F",
        ): f"<title>Genesis - The Vault</title><table>{queue_rows}</table>",
        ("vimm.net", "/vault/31"): download_form(31),
        ("vimm.net", "/vault/32"): download_form(32),
        ("vimm.net", "/vault/33"): download_form(33),
        ("coolrom.com", "/roms/genesis/D/"): f"<title>Genesis - D</title>{cool}",
        ("www.consoleroms.com", "/roms/sega-genesis"): f"<title>Genesis</title>{console}",
        (
            "www.emu-land.net",
            "/en/consoles/genesis/roms/d",
        ): f'<title>Genesis - D</title><a href="/en/consoles/genesis/roms/e">E</a>{emu}',
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
    shutil.copytree(EXTENSION, target)
    manifest = json.loads((target / "manifest.json").read_text())
    manifest["host_permissions"] = [f"{base}/*"]
    manifest["permissions"] = [*manifest["permissions"], "downloads"]
    (target / "manifest.json").write_text(json.dumps(manifest))
    script = target / "content" / "vimm.js"
    source = script.read_text()
    patched = source.replace("const GAP_MS = 15000;", "const GAP_MS = 100;")
    if patched == source:
        raise SystemExit("GAP_MS not found in content/vimm.js")
    script.write_text(patched)
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
    expected = [
        "Alpha Quest In library (approximate)",
        "Beta Quest Missing (approximate)",
        "Zeta Quest Not in any DAT",
        "Omega Quest Not wanted (approximate)",
    ]
    problems = []
    for url in ("https://vimm.net/vault/?p=list&system=GB&q=", "https://vimm.net/vault/GB/A"):
        page = context.new_page()
        page.goto(url)
        found = badges(page, 4)
        page.close()
        if found != expected:
            problems.append(f"vimm list {url}: {found}")
    return problems


STUB_DOWNLOADS = """() => {
  chrome.downloads.search = async ({ id, url }) => {
    const number = id ?? Number(new URL(url).searchParams.get("mediaId")) - 30;
    return [
      {
        id: number,
        state: globalThis.stubState ?? "complete",
        filename: `/saved/romledger/Game ${number}.zip`,
      },
    ];
  };
}"""


def check_vimm_queue(context: BrowserContext, worker: Worker) -> list[str]:
    """Stubs the downloads search: file routing is covered by check_vimm_download."""
    worker.evaluate("chrome.storage.local.set({ routeDownloads: true })")
    worker.evaluate(STUB_DOWNLOADS)
    passed = {"check": False}
    requests: list[tuple[str, str]] = []

    def serve_download(route: Route) -> None:
        referer = route.request.headers.get("referer", "")
        requests.append((route.request.url, referer))
        if referer.startswith("https://vimm.net/"):
            route.fulfill(
                status=200,
                headers={
                    "Content-Type": "application/zip",
                    "Content-Disposition": 'attachment; filename="Game.zip"',
                },
                body="PK",
            )
        else:
            route.fulfill(status=500, body="no referer")

    def withhold_form(route: Route) -> None:
        if passed["check"]:
            route.fallback()
        else:
            route.fulfill(status=200, content_type="text/html", body="<body>Checking</body>")

    context.route("https://vimm.net/vault/32", withhold_form)
    context.route("https://dl3.vimm.net/**", serve_download)
    page = context.new_page()
    page.goto("https://vimm.net/vault/Genesis/F")
    panel = page.locator(".romledger-panel")
    start = panel.get_by_role("button", name="Download 3 missing")
    start.wait_for(timeout=10000)
    problems = []
    if "1 matched by title" not in panel.inner_text():
        problems.append(f"vimm queue approximate count: {panel.inner_text()!r}")
    start.click()
    resume = panel.get_by_role("button", name="Resume")
    resume.wait_for(timeout=10000)
    if [url for url, _ in requests] != ["https://dl3.vimm.net/?mediaId=31&token=token31"]:
        problems.append("vimm queue: the first download did not run alone before the pause")
    passed["check"] = True
    resume.click()
    page.wait_for_function(
        "document.querySelector('.romledger-panel').innerText.includes('Finished.')", timeout=10000
    )
    text = panel.inner_text()
    expected = [f"/saved/romledger/Game {n}.zip" for n in (1, 2, 3)]
    if any(path not in text for path in expected):
        problems.append(f"vimm queue saved paths: {text!r}")
    expected = [f"https://dl3.vimm.net/?mediaId={n}&token=token{n}" for n in (31, 32, 33)]
    if [url for url, _ in requests] != expected:
        problems.append(f"vimm queue downloads: {requests}")
    if any(not referer.startswith("https://vimm.net/") for _, referer in requests):
        problems.append(f"vimm queue referers: {requests}")
    page.close()
    context.unroute("https://dl3.vimm.net/**", serve_download)
    context.unroute("https://vimm.net/vault/32", withhold_form)
    return problems


HTTP_TOO_MANY = 429
LATER_GAMES = re.compile(r"https://vimm\.net/vault/3[23]$")


def run_stopped_queue(
    context: BrowserContext, worker: Worker, game_status: int, download_state: str
) -> tuple[str, list[str], list[str]]:
    seen: list[str] = []
    worker.evaluate(f'globalThis.stubState = "{download_state}"')

    def record(route: Route) -> None:
        seen.append(route.request.url)
        route.fulfill(status=200, headers={"Content-Disposition": "attachment"}, body="PK")

    def answer(route: Route) -> None:
        seen.append(route.request.url)
        if game_status == HTTP_TOO_MANY:
            route.fulfill(status=game_status, body="Too many requests")
        else:
            route.fallback()

    context.route("https://dl3.vimm.net/**", record)
    context.route(LATER_GAMES, answer)
    page = context.new_page()
    page.goto("https://vimm.net/vault/Genesis/F")
    panel = page.locator(".romledger-panel")
    panel.get_by_role("button", name="Download 3 missing").click()
    page.wait_for_function(
        "document.querySelector('.romledger-panel').innerText.includes('Stopped')", timeout=10000
    )
    page.wait_for_timeout(500)
    text = panel.inner_text()
    titles = panel.locator(".romledger-badge").evaluate_all("(nodes) => nodes.map((n) => n.title)")
    page.close()
    context.unroute("https://dl3.vimm.net/**", record)
    context.unroute(LATER_GAMES, answer)
    worker.evaluate("delete globalThis.stubState")
    return text, titles, seen


def check_vimm_queue_stops(context: BrowserContext, worker: Worker) -> list[str]:
    """A 429 on a game page and a failed download each stop the queue before the later games."""
    first = "https://dl3.vimm.net/?mediaId=31&token=token31"
    cases = (
        ("slow down", HTTP_TOO_MANY, "complete", "Vimm's Lair says to slow down.", 2),
        ("failed download", 200, "interrupted", "interrupted", 1),
    )
    problems = []
    for name, game_status, download_state, title, requests in cases:
        text, titles, seen = run_stopped_queue(context, worker, game_status, download_state)
        stopped = "Stopped after a failed download." in text
        if not stopped or not any(title in found for found in titles) or len(seen) != requests:
            problems.append(f"vimm queue {name}: {text!r} {titles} {seen}")
        if seen[0] != first:
            problems.append(f"vimm queue {name}: first request {seen}")
    return problems


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class ZipHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="Game (USA).zip"')
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"PK")

    def log_message(self, *_args: object) -> None:
        pass


DOWNLOAD_SCRIPT = """async (url) => {
  const id = await chrome.downloads.download({ url });
  for (let tries = 0; tries < 100; tries += 1) {
    const [item] = await chrome.downloads.search({ id });
    if (item.state !== "in_progress") {
      return item.filename;
    }
    await new Promise((done) => setTimeout(done, 100));
  }
  return "timeout";
}"""


def is_romledger(worker: Worker) -> bool:
    try:
        return worker.evaluate("chrome.runtime.getManifest().name") == "romledger"
    except Error:
        return False


def check_vimm_download(playwright: Playwright, directory: Path, extension: Path) -> list[str]:
    """Runs a browser Playwright does not steer: its download handling replaces the file names."""
    saved_to = directory / "downloads"
    preferences = directory / "download-profile" / "Default" / "Preferences"
    preferences.parent.mkdir(parents=True)
    preferences.write_text(
        json.dumps({"download": {"default_directory": str(saved_to), "prompt_for_download": False}})
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), ZipHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port, debug_port = server.server_address[1], free_port()
    browser = subprocess.Popen(  # noqa: S603
        [
            playwright.chromium.executable_path,
            "--headless=new",
            f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={directory / 'download-profile'}",
            f"--disable-extensions-except={extension}",
            f"--load-extension={extension}",
            "--disable-features=DisableLoadExtensionCommandLineSwitch",
            "--host-resolver-rules=MAP dl3.vimm.net 127.0.0.1",
            "--no-sandbox",
            "--use-mock-keychain",
            "--password-store=basic",
            "--no-first-run",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                connected = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{debug_port}")
                break
            except Error:
                time.sleep(0.1)
        else:
            return ["vimm download: the browser did not start"]
        connected.new_browser_cdp_session().send(
            "Browser.setDownloadBehavior", {"behavior": "default"}
        )
        context = connected.contexts[0]
        worker = None
        for _ in range(100):
            worker = next((w for w in context.service_workers if is_romledger(w)), None)
            if worker:
                break
            time.sleep(0.1)
        if worker is None:
            return ["vimm download: the extension did not load"]
        worker.evaluate("chrome.storage.local.set({ routeDownloads: true })")
        saved = worker.evaluate(DOWNLOAD_SCRIPT, f"http://dl3.vimm.net:{port}/?mediaId=9&token=t")
        connected.close()
    finally:
        browser.terminate()
        browser.wait()
        server.shutdown()
    return (
        []
        if saved == str(saved_to / "romledger" / "Game (USA).zip")
        else [f"vimm download: {saved}"]
    )


def check_coolrom(context: BrowserContext) -> list[str]:
    page = context.new_page()
    page.goto("https://coolrom.com/roms/genesis/D/")
    found = badges(page, 2)
    page.close()
    expected = ["Delta Run (USA) In library", "Echo Run (USA) Missing"]
    return [] if found == expected else [f"coolrom: {found}"]


def check_consoleroms(context: BrowserContext) -> list[str]:
    page = context.new_page()
    page.goto("https://www.consoleroms.com/roms/sega-genesis")
    found = badges(page, 2)
    page.close()
    expected = ["Delta Run (USA) In library", "Echo Run (USA) Missing"]
    return [] if found == expected else [f"consoleroms: {found}"]


def check_emuland(context: BrowserContext) -> list[str]:
    page = context.new_page()
    page.goto("https://www.emu-land.net/en/consoles/genesis/roms/d")
    found = badges(page, 2)
    page.close()
    expected = ["Delta Run (USA) In library", "Echo Run (USA) Missing"]
    return [] if found == expected else [f"emuland: {found}"]


def check_archive(context: BrowserContext) -> list[str]:
    problems = []
    page = context.new_page()
    page.goto(f"https://archive.org/details/{ITEM}")
    found = badges(page, 1)
    if "of 3 wanted games" not in found[0]:
        problems.append(f"archive {ITEM}: {found}")
    page.goto("https://archive.org/details/other")
    page.wait_for_timeout(1500)
    if page.locator(".romledger-panel").count():
        problems.append("archive other: a panel appeared on an unrelated item")
    page.close()
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
            re.compile(
                r"https://(vimm\.net|coolrom\.com|www\.consoleroms\.com|www\.emu-land\.net"
                r"|archive\.org)/.*"
            ),
            serve_fixture,
        )
        problems = (
            check_vimm_game(context)
            + check_vimm_list(context)
            + check_coolrom(context)
            + check_consoleroms(context)
            + check_emuland(context)
            + check_archive(context)
            + check_popup(context, extension_id, output)
            + check_vimm_queue(context, worker)
            + check_vimm_queue_stops(context, worker)
            + check_unreachable(context, extension_id, worker)
            + check_vimm_download(playwright, directory, extension)
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
