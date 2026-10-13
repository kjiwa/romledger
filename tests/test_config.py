from pathlib import Path

import pytest

from rom_scraper import config

VALID = """\
[library]
roms = "{roms}"
inboxes = ["{inbox}"]

[platforms.nes]
dat = "no-intro/Nintendo - Nintendo Entertainment System"
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def valid_text(tmp_path: Path) -> str:
    return VALID.format(roms=tmp_path / "roms", inbox=tmp_path / "inbox")


def test_load_valid(tmp_path: Path) -> None:
    loaded = config.load(write(tmp_path, valid_text(tmp_path)))
    assert loaded.library.roms == tmp_path / "roms"
    assert loaded.library.inboxes == (tmp_path / "inbox",)
    assert loaded.platforms["nes"].dat.endswith("Entertainment System")


def test_platform_defaults(tmp_path: Path) -> None:
    platform = config.load(write(tmp_path, valid_text(tmp_path))).platforms["nes"]
    assert platform.regions == ("USA", "World")
    assert platform.languages == ("En",)


def test_platform_overrides(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + 'regions = ["Europe"]\nlanguages = ["Fr"]\n'
    platform = config.load(write(tmp_path, text)).platforms["nes"]
    assert platform.regions == ("Europe",)
    assert platform.languages == ("Fr",)


def test_unknown_key(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace("[platforms.nes]", "[platforms.nes]\nbogus = 1")
    path = write(tmp_path, text)
    with pytest.raises(config.ConfigError) as error:
        config.load(path)
    message = str(error.value)
    assert str(path) in message
    assert "platforms.nes.bogus" in message


def test_unknown_top_level_key(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match="unknown key hooks"):
        config.load(write(tmp_path, valid_text(tmp_path) + "\n[hooks]\n"))


def test_wrong_type(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace('inboxes = ["', 'inboxes = "').replace('"]', '"')
    with pytest.raises(
        config.ConfigError, match=r"library\.inboxes must be a list of non-empty strings"
    ):
        config.load(write(tmp_path, text))


def test_wrong_type_string(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace('dat = "', "dat = 5 #")
    with pytest.raises(config.ConfigError, match=r"platforms\.nes\.dat must be a non-empty string"):
        config.load(write(tmp_path, text))


def test_platforms_entry_not_table(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace("[platforms.nes]", "[platforms]\nnes = 1\n#")
    with pytest.raises(config.ConfigError, match=r"platforms\.nes must be a table"):
        config.load(write(tmp_path, text))


def test_library_not_table(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match="library must be a table"):
        config.load(write(tmp_path, "library = 1\n"))


def test_missing_library(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match=r"missing \[library\]"):
        config.load(write(tmp_path, ""))


def test_missing_roms(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match=r"missing library\.roms"):
        config.load(write(tmp_path, '[library]\ninboxes = ["/x"]\n'))


def test_missing_inboxes(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match=r"missing library\.inboxes"):
        config.load(write(tmp_path, '[library]\nroms = "/x"\n'))


def test_empty_inboxes(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match=r"library\.inboxes is empty"):
        config.load(write(tmp_path, '[library]\nroms = "/x"\ninboxes = []\n'))


def test_invalid_toml(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match="invalid TOML"):
        config.load(write(tmp_path, "[library"))


def test_tilde_expansion(tmp_path: Path) -> None:
    text = '[library]\nroms = "~/roms"\ninboxes = ["~/inbox"]\n'
    loaded = config.load(write(tmp_path, text))
    assert loaded.library.roms == Path.home() / "roms"
    assert loaded.library.inboxes == (Path.home() / "inbox",)


def test_resolve_prefers_argument(tmp_path: Path) -> None:
    arg = write(tmp_path, "")
    env_file = tmp_path / "env.toml"
    env_file.write_text("")
    assert config.resolve_path(str(arg), {config.CONFIG_ENV: str(env_file)}) == arg


def test_resolve_env_over_xdg(tmp_path: Path) -> None:
    env_file = tmp_path / "env.toml"
    env_file.write_text("")
    env = {config.CONFIG_ENV: str(env_file), "XDG_CONFIG_HOME": str(tmp_path)}
    assert config.resolve_path(None, env) == env_file


def test_resolve_xdg(tmp_path: Path) -> None:
    target = tmp_path / "rom-scraper" / "config.toml"
    target.parent.mkdir()
    target.write_text("")
    assert config.resolve_path(None, {"XDG_CONFIG_HOME": str(tmp_path)}) == target


def test_resolve_default_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    target = tmp_path / ".config" / "rom-scraper" / "config.toml"
    target.parent.mkdir(parents=True)
    target.write_text("")
    assert config.resolve_path(None, {}) == target


def test_resolve_missing_file(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError) as error:
        config.resolve_path(None, {"XDG_CONFIG_HOME": str(tmp_path)})
    message = str(error.value)
    assert str(tmp_path / "rom-scraper" / "config.toml") in message
    assert "not found" in message
    assert "[library]" in message


def test_check_library_ok(tmp_path: Path) -> None:
    (tmp_path / "roms").mkdir()
    (tmp_path / "inbox").mkdir()
    config.check_library(config.load(write(tmp_path, valid_text(tmp_path))))


def test_check_library_missing_roms(tmp_path: Path) -> None:
    loaded = config.load(write(tmp_path, valid_text(tmp_path)))
    with pytest.raises(config.ConfigError, match=r"not a directory.*NAS share mounted"):
        config.check_library(loaded)


def test_check_library_missing_inbox(tmp_path: Path) -> None:
    (tmp_path / "roms").mkdir()
    loaded = config.load(write(tmp_path, valid_text(tmp_path)))
    with pytest.raises(config.ConfigError, match=r"inbox: not a directory"):
        config.check_library(loaded)


def test_relative_path_rejected(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace(str(tmp_path / "roms"), "roms")
    with pytest.raises(config.ConfigError, match=r"library\.roms 'roms' is not absolute"):
        config.load(write(tmp_path, text))


def test_unknown_user_home_rejected(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace(str(tmp_path / "roms"), "~no-such-user-xyz/roms")
    with pytest.raises(config.ConfigError, match=r"library\.roms"):
        config.load(write(tmp_path, text))


def test_empty_list_item_rejected(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + 'regions = [""]\n'
    with pytest.raises(config.ConfigError, match="non-empty strings"):
        config.load(write(tmp_path, text))


def test_non_utf8_file_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(config.ConfigError, match="cannot read the file"):
        config.load(path)
