import base64
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from romledger import config, extension, native

ROOT = Path(__file__).resolve().parent.parent


def home_with(tmp_path: Path, *roots: str, platform: str = "linux") -> Path:
    home = tmp_path / "home"
    base = home / ("Library/Application Support" if platform == "darwin" else ".config")
    for root in roots:
        (base / root).mkdir(parents=True)
    return home


@pytest.fixture(autouse=True)
def linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")


def test_the_extension_id_matches_the_key_in_its_manifest() -> None:
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text())
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    assert "".join(chr(ord("a") + int(char, 16)) for char in digest) == extension.EXTENSION_ID


def test_the_gecko_id_matches_the_manifest() -> None:
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text())
    assert manifest["browser_specific_settings"]["gecko"]["id"] == extension.GECKO_ID
    assert "nativeMessaging" in manifest["permissions"]


def test_the_host_name_follows_the_naming_rules() -> None:
    assert native.HOST_NAME.islower()
    assert all(part.isalnum() for part in native.HOST_NAME.split("."))


def test_linux_manifests_live_in_each_browsers_own_directory(tmp_path: Path) -> None:
    home = tmp_path / "home"
    found = {browser.name: browser.manifest for browser in extension.browsers(home, "linux")}
    assert (
        found["Chrome"] == home / ".config/google-chrome/NativeMessagingHosts" / extension.MANIFEST
    )
    assert found["Firefox"] == home / ".mozilla/native-messaging-hosts" / extension.MANIFEST
    assert found["Edge"].parent.parent.name == "microsoft-edge"


def test_macos_manifests(tmp_path: Path) -> None:
    home = tmp_path / "home"
    base = home / "Library" / "Application Support"
    found = {browser.name: browser.manifest for browser in extension.browsers(home, "darwin")}
    assert found["Chrome"] == base / "Google/Chrome/NativeMessagingHosts" / extension.MANIFEST
    assert found["Firefox"] == base / "Mozilla/NativeMessagingHosts" / extension.MANIFEST
    assert "Brave" in found


def test_windows_is_refused(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match="macOS and Linux only"):
        extension.browsers(tmp_path, "win32")


def test_the_launcher_sets_the_config_and_runs_the_host() -> None:
    text = extension.launcher_text("/opt/py thon/bin/python", Path("/home/u/my config.toml"), None)
    assert text == (
        "#!/bin/sh\n"
        "export ROMLEDGER_CONFIG='/home/u/my config.toml'\n"
        "exec '/opt/py thon/bin/python' -m romledger.native \"$@\"\n"
    )


def test_the_launcher_keeps_an_explicit_data_directory() -> None:
    text = extension.launcher_text("python", Path("/c.toml"), Path("/data"))
    assert "export ROMLEDGER_DATA=/data\n" in text


def test_a_chromium_manifest_allows_only_this_extension(tmp_path: Path) -> None:
    chrome = extension.browsers(tmp_path, "linux")[0]
    manifest = extension.manifest_for(chrome, Path("/x/native-host"))
    assert manifest == {
        "name": "io.github.kjiwa.romledger",
        "description": manifest["description"],
        "path": "/x/native-host",
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension.EXTENSION_ID}/"],
    }


def test_a_firefox_manifest_names_the_add_on(tmp_path: Path) -> None:
    firefox = extension.browsers(tmp_path, "linux")[-1]
    manifest = extension.manifest_for(firefox, Path("/x/native-host"))
    assert manifest["allowed_extensions"] == [extension.GECKO_ID]
    assert "allowed_origins" not in manifest


def test_install_writes_a_manifest_only_for_browsers_that_exist(tmp_path: Path) -> None:
    home = home_with(tmp_path, "google-chrome", "chromium")
    data = tmp_path / "data"
    installed = extension.install(Path("/c.toml"), data, home, python="/py")
    assert [browser.name for browser in installed] == ["Chrome", "Chromium"]
    chrome = home / ".config/google-chrome/NativeMessagingHosts" / extension.MANIFEST
    assert json.loads(chrome.read_text())["path"] == str(data / "native-host")
    assert not (home / ".config/microsoft-edge").exists()
    launcher = data / "native-host"
    assert launcher.read_text().endswith('exec /py -m romledger.native "$@"\n')
    assert launcher.stat().st_mode & stat.S_IXUSR


def test_install_without_a_browser_says_what_it_looked_for(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match=r"no supported browser found \(looked for Chrome"):
        extension.install(Path("/c.toml"), tmp_path / "data", tmp_path / "home")
    assert not (tmp_path / "data" / "native-host").exists()


def test_install_twice_replaces_the_files(tmp_path: Path) -> None:
    home = home_with(tmp_path, "chromium")
    data = tmp_path / "data"
    extension.install(Path("/a.toml"), data, home)
    extension.install(Path("/b.toml"), data, home)
    assert "/b.toml" in (data / "native-host").read_text()


def test_uninstall_removes_every_manifest_and_the_launcher(tmp_path: Path) -> None:
    home = home_with(tmp_path, "google-chrome", "chromium")
    data = tmp_path / "data"
    extension.install(Path("/c.toml"), data, home)
    removed = extension.uninstall(data, home)
    assert [browser.name for browser in removed] == ["Chrome", "Chromium"]
    assert not (data / "native-host").exists()
    assert extension.uninstall(data, home) == []


def test_status_tells_each_browser_apart(tmp_path: Path) -> None:
    home = home_with(tmp_path, "google-chrome", "chromium")
    data = tmp_path / "data"
    extension.install(Path("/c.toml"), data, home)
    (home / ".config/chromium/NativeMessagingHosts" / extension.MANIFEST).unlink()
    states = {
        result.browser.name: result.state
        for result in extension.status(data, home, lambda launcher: None)
    }
    assert states["Chrome"] == "ready"
    assert states["Chromium"] == "not installed"
    assert states["Edge"] == "not found"


def test_status_reports_a_host_that_does_not_answer(tmp_path: Path) -> None:
    home = home_with(tmp_path, "google-chrome")
    data = tmp_path / "data"
    extension.install(Path("/c.toml"), data, home)
    result = extension.status(data, home, lambda launcher: "it crashed")[0]
    assert result.state == "broken: it crashed"


def test_status_reports_a_manifest_that_points_elsewhere(tmp_path: Path) -> None:
    home = home_with(tmp_path, "google-chrome")
    extension.install(Path("/c.toml"), tmp_path / "old", home)
    result = extension.status(tmp_path / "new", home, lambda launcher: None)[0]
    assert result.state.startswith("stale: it points at ")
    assert result.state.endswith("run romledger extension install")


@pytest.mark.parametrize("text", ["not json", "[]", '{"name": "x"}'])
def test_status_reports_an_unreadable_manifest(tmp_path: Path, text: str) -> None:
    home = home_with(tmp_path, "google-chrome")
    manifest = home / ".config/google-chrome/NativeMessagingHosts" / extension.MANIFEST
    manifest.parent.mkdir()
    manifest.write_text(text)
    result = extension.status(tmp_path / "data", home, lambda launcher: None)[0]
    assert result.state == "broken: the host manifest cannot be read"


def test_the_installed_launcher_answers_a_ping(tmp_path: Path) -> None:
    home = home_with(tmp_path, "chromium")
    data = tmp_path / "data"
    roms, inbox = tmp_path / "roms", tmp_path / "inbox"
    roms.mkdir()
    inbox.mkdir()
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'[library]\nroms = "{roms}"\ninboxes = ["{inbox}"]\n')
    extension.install(cfg, data, home)
    assert extension.ping_host(data / "native-host") is None
    result = extension.status(data, home)[1]
    assert (result.browser.name, result.state) == ("Chromium", "ready")


def test_ping_reports_a_missing_launcher(tmp_path: Path) -> None:
    problem = extension.ping_host(tmp_path / "native-host")
    assert problem is not None
    assert "run romledger extension install" in problem


def test_ping_reports_a_launcher_that_cannot_run(tmp_path: Path) -> None:
    launcher = tmp_path / "native-host"
    launcher.write_text("#!/nonexistent/interpreter\n")
    launcher.chmod(0o755)
    problem = extension.ping_host(launcher)
    assert problem is not None
    assert problem.startswith("the host did not answer")


def test_ping_reports_garbage_from_the_host(tmp_path: Path) -> None:
    launcher = tmp_path / "native-host"
    launcher.write_text("#!/bin/sh\nprintf '\\005\\000\\000\\000hello'\n")
    launcher.chmod(0o755)
    assert extension.ping_host(launcher) == "the host answered with something that is not a message"


def test_ping_reports_an_error_answer(tmp_path: Path) -> None:
    launcher = tmp_path / "native-host"
    body = '{"ok":false,"error":"roms: not a directory"}'
    launcher.write_text(f"#!/bin/sh\nprintf '\\055\\000\\000\\000%s' '{body}'\n")
    launcher.chmod(0o755)
    assert extension.ping_host(launcher) == "roms: not a directory"


def test_ping_reports_a_host_that_says_nothing(tmp_path: Path) -> None:
    launcher = tmp_path / "native-host"
    launcher.write_text("#!/bin/sh\nexit 3\n")
    launcher.chmod(0o755)
    assert extension.ping_host(launcher) == "the host answered with something that is not a message"
    assert os.access(launcher, os.X_OK)
