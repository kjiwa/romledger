import json
import os
import shlex
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from romledger import config, native

# The ID Chromium gives the unpacked extension: its manifest carries a fixed public key.
EXTENSION_ID = "bnpeebfkanfigeilgcclmgjghnnphknc"
GECKO_ID = "romledger@romledger.invalid"
LAUNCHER = "native-host"
MANIFEST = f"{native.HOST_NAME}.json"
HOSTS_DIR = "NativeMessagingHosts"
PING_SECONDS = 20

# (name, family, data directory below the platform's base, host manifest directory)
MACOS = [
    ("Chrome", "chromium", "Google/Chrome", HOSTS_DIR),
    ("Chromium", "chromium", "Chromium", HOSTS_DIR),
    ("Brave", "chromium", "BraveSoftware/Brave-Browser", HOSTS_DIR),
    ("Edge", "chromium", "Microsoft Edge", HOSTS_DIR),
    ("Firefox", "firefox", "Mozilla", HOSTS_DIR),
]
LINUX = [
    ("Chrome", "chromium", "google-chrome", HOSTS_DIR),
    ("Chromium", "chromium", "chromium", HOSTS_DIR),
    ("Brave", "chromium", "BraveSoftware/Brave-Browser", HOSTS_DIR),
    ("Edge", "chromium", "microsoft-edge", HOSTS_DIR),
]


@dataclass(frozen=True)
class Browser:
    name: str
    family: str
    root: Path
    manifest: Path

    @property
    def found(self) -> bool:
        return self.root.is_dir()


def browsers(home: Path, platform: str | None = None) -> list[Browser]:
    platform = platform or sys.platform
    if platform == "win32":
        raise config.ConfigError(
            "the browser extension talks to romledger through a native host, which romledger "
            "installs on macOS and Linux only."
        )
    if platform == "darwin":
        base = home / "Library" / "Application Support"
        table = MACOS
        firefox = None
    else:
        base = home / ".config"
        table = LINUX
        firefox = Browser(
            "Firefox",
            "firefox",
            home / ".mozilla",
            home / ".mozilla" / "native-messaging-hosts" / MANIFEST,
        )
    found = [
        Browser(name, family, base / root, base / root / directory / MANIFEST)
        for name, family, root, directory in table
    ]
    return [*found, *([firefox] if firefox else [])]


def launcher_path(data_dir: Path) -> Path:
    return data_dir / LAUNCHER


def launcher_text(python: str, config_file: Path, data_dir: Path | None) -> str:
    lines = ["#!/bin/sh", f"export ROMLEDGER_CONFIG={shlex.quote(str(config_file))}"]
    if data_dir is not None:
        lines.append(f"export ROMLEDGER_DATA={shlex.quote(str(data_dir))}")
    lines.append(f'exec {shlex.quote(python)} -m romledger.native "$@"')
    return "\n".join(lines) + "\n"


def manifest_for(browser: Browser, launcher: Path) -> dict[str, object]:
    origin: dict[str, object] = (
        {"allowed_extensions": [GECKO_ID]}
        if browser.family == "firefox"
        else {"allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"]}
    )
    return {
        "name": native.HOST_NAME,
        "description": "romledger: tells the browser extension what your library has",
        "path": str(launcher),
        "type": "stdio",
        **origin,
    }


def install(
    config_file: Path,
    data_dir: Path,
    home: Path | None = None,
    python: str = sys.executable,
    explicit_data: bool = False,
) -> list[Browser]:
    present = [browser for browser in browsers(home or Path.home()) if browser.found]
    if not present:
        names = ", ".join(browser.name for browser in browsers(home or Path.home()))
        raise config.ConfigError(f"no supported browser found (looked for {names}).")
    launcher = launcher_path(data_dir)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(launcher_text(python, config_file, data_dir if explicit_data else None))
    launcher.chmod(0o755)
    for browser in present:
        browser.manifest.parent.mkdir(parents=True, exist_ok=True)
        browser.manifest.write_text(json.dumps(manifest_for(browser, launcher), indent=2) + "\n")
    return present


def uninstall(data_dir: Path, home: Path | None = None) -> list[Browser]:
    removed = []
    for browser in browsers(home or Path.home()):
        if browser.manifest.is_file():
            browser.manifest.unlink()
            removed.append(browser)
    launcher_path(data_dir).unlink(missing_ok=True)
    return removed


@dataclass(frozen=True)
class Status:
    browser: Browser
    state: str


def status(
    data_dir: Path,
    home: Path | None = None,
    ping: Callable[[Path], str | None] | None = None,
) -> list[Status]:
    check = ping or ping_host
    launcher = launcher_path(data_dir)
    results = []
    for browser in browsers(home or Path.home()):
        if not browser.found:
            results.append(Status(browser, "not found"))
        elif not browser.manifest.is_file():
            results.append(Status(browser, "not installed"))
        else:
            results.append(Status(browser, _manifest_state(browser, launcher, check)))
    return results


def _manifest_state(browser: Browser, launcher: Path, check: Callable[[Path], str | None]) -> str:
    try:
        target = Path(json.loads(browser.manifest.read_text())["path"])
    except (OSError, ValueError, KeyError, TypeError):
        return "broken: the host manifest cannot be read"
    if target != launcher:
        return f"stale: it points at {target}; run romledger extension install"
    problem = check(target)
    return "ready" if problem is None else f"broken: {problem}"


def ping_host(launcher: Path) -> str | None:
    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        return f"{launcher} is missing; run romledger extension install"
    request = json.dumps({"id": 1, "type": "ping"}).encode()
    framed = native.LENGTH.pack(len(request)) + request
    try:
        done = subprocess.run(  # noqa: S603
            [str(launcher)],
            input=framed,
            capture_output=True,
            timeout=PING_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"the host did not answer ({error})"
    (size,) = native.LENGTH.unpack(done.stdout[: native.LENGTH.size] or b"\0\0\0\0")
    try:
        answer = json.loads(done.stdout[native.LENGTH.size : native.LENGTH.size + size])
    except ValueError:
        return "the host answered with something that is not a message"
    return None if answer.get("ok") is True else str(answer.get("error", "no answer"))
