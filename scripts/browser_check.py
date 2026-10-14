"""Check keyboard navigation and drag-and-drop upload against the demo dashboard.

Run through scripts/browser-check.sh, which supplies Playwright and romledger.
"""

import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin

from demo_library import PAGES, TOKEN, build, serve
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from romledger import dats
from romledger.context import load_context

MAX_TABS = 400
FOCUSABLE = "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled])"
DROP = """(name) => {
    const data = new DataTransfer();
    data.items.add(new File(["dropped"], name));
    document.querySelector("[data-dropzone]").dispatchEvent(
        new DragEvent("drop", { dataTransfer: data, bubbles: true, cancelable: true }));
}"""
FOCUS_STATE = """() => {
    const element = document.activeElement;
    const style = getComputedStyle(element);
    const label = element.type === "file" && element.labels[0];
    const ring = label ? getComputedStyle(label) : style;
    const fresh = element.dataset.visited !== "yes";
    element.dataset.visited = "yes";
    return {
        key: element.outerHTML.slice(0, 80),
        fresh,
        ring: parseFloat(ring.outlineWidth) > 0 && ring.outlineStyle !== "none",
    };
}"""


def tab_through(page: Page, path: str) -> list[str]:
    problems = []
    page.goto(urljoin(page.url, path))
    for _ in range(MAX_TABS):
        page.keyboard.press("Tab")
        state = page.evaluate(FOCUS_STATE)
        if not state["fresh"] or state["key"].startswith("<body"):
            break
        if not state["ring"]:
            problems.append(f"{path}: no focus ring on {state['key']}")
    unreached = page.eval_on_selector_all(
        FOCUSABLE,
        "(nodes) => nodes.filter((node) => node.getClientRects().length"
        ' && node.dataset.visited !== "yes").map((node) => node.outerHTML.slice(0, 80))',
    )
    problems += [f"{path}: Tab never reached {key}" for key in unreached]
    return problems


def drop_upload(page: Page, base: str, inbox: Path) -> list[str]:
    page.goto(f"{base}/inbox")
    page.evaluate(DROP, "Dropped Game (USA).nes")
    problems = []
    try:
        page.wait_for_url("**/inbox?uploaded=1")
    except PlaywrightTimeoutError:
        return ["drop: upload did not finish: " + page.inner_text("#upload-list")]
    if not (inbox / "Dropped Game (USA).nes").is_file():
        problems.append("drop: file did not reach the inbox")
    if "Dropped Game (USA).nes" not in page.inner_text(".files"):
        problems.append("drop: inbox list does not show the file")
    return problems


def import_form(page: Page, base: str) -> list[str]:
    page.goto(f"{base}/inbox")
    page.click("form[action='/import'] button")
    try:
        page.wait_for_url("**/activity")
    except PlaywrightTimeoutError:
        return ["import: form post did not reach /activity: " + page.inner_text("body")[:200]]
    return []


def touch_dats() -> None:
    context = load_context(None)
    for platform in context.config.platforms.values():
        path = dats.dat_path(context.data_dir, platform.dat)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


def main() -> int:
    problems = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        build(root)
        touch_dats()
        server, base = serve(
            igir_report=lambda *args, **kwargs: [],
            igir_move=lambda *args: None,
            hook=lambda argv: 0,
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.goto(f"{base}/?token={TOKEN}")
            for path in PAGES.values():
                problems += tab_through(page, path)
            problems += drop_upload(page, base, root / "inbox")
            problems += import_form(page, base)
            browser.close()
        server.should_exit = True
        time.sleep(0.5)
    for problem in problems:
        print(problem)
    print("browser checks: " + ("FAILED" if problems else "ok"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
