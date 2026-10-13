from pathlib import Path

import pytest

from rom_scraper import config, registry

VALID = """\
[library]
roms = "{roms}"
inboxes = ["{inbox}"]

[platforms.nes]
dat = "no-intro/Nintendo - Nintendo Entertainment System"
"""


def load(path: Path) -> config.Config:
    return config.load(path, registry.load())


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def valid_text(tmp_path: Path) -> str:
    return VALID.format(roms=tmp_path / "roms", inbox=tmp_path / "inbox")


def test_load_valid(tmp_path: Path) -> None:
    loaded = load(write(tmp_path, valid_text(tmp_path)))
    assert loaded.library.roms == tmp_path / "roms"
    assert loaded.library.inboxes == (tmp_path / "inbox",)
    assert loaded.platforms["nes"].dat.endswith("Entertainment System")


def test_platform_defaults(tmp_path: Path) -> None:
    platform = load(write(tmp_path, valid_text(tmp_path))).platforms["nes"]
    assert platform.regions == ("USA", "WORLD")
    assert platform.languages == ("EN",)


def test_platform_overrides(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + 'regions = ["EUR"]\nlanguages = ["FR"]\n'
    platform = load(write(tmp_path, text)).platforms["nes"]
    assert platform.regions == ("EUR",)
    assert platform.languages == ("FR",)


def test_unknown_key(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace("[platforms.nes]", "[platforms.nes]\nbogus = 1")
    path = write(tmp_path, text)
    with pytest.raises(config.ConfigError) as error:
        load(path)
    message = str(error.value)
    assert str(path) in message
    assert "platforms.nes.bogus" in message


def test_unknown_top_level_key(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match="unknown key hooks"):
        load(write(tmp_path, valid_text(tmp_path) + "\n[hooks]\n"))


def test_wrong_type(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace('inboxes = ["', 'inboxes = "').replace('"]', '"')
    with pytest.raises(
        config.ConfigError, match=r"library\.inboxes must be a list of non-empty strings"
    ):
        load(write(tmp_path, text))


def test_wrong_type_string(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace('dat = "', "dat = 5 #")
    with pytest.raises(config.ConfigError, match=r"platforms\.nes\.dat must be a non-empty string"):
        load(write(tmp_path, text))


def test_platforms_entry_not_table(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace("[platforms.nes]", "[platforms]\nnes = 1\n#")
    with pytest.raises(config.ConfigError, match=r"platforms\.nes must be a table"):
        load(write(tmp_path, text))


def test_library_not_table(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match="library must be a table"):
        load(write(tmp_path, "library = 1\n"))


def test_missing_library(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match=r"missing \[library\]"):
        load(write(tmp_path, ""))


def test_missing_roms(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match=r"missing library\.roms"):
        load(write(tmp_path, '[library]\ninboxes = ["/x"]\n'))


def test_missing_inboxes(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match=r"missing library\.inboxes"):
        load(write(tmp_path, '[library]\nroms = "/x"\n'))


def test_empty_inboxes(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match=r"library\.inboxes is empty"):
        load(write(tmp_path, '[library]\nroms = "/x"\ninboxes = []\n'))


def test_invalid_toml(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match="invalid TOML"):
        load(write(tmp_path, "[library"))


def test_tilde_expansion(tmp_path: Path) -> None:
    text = '[library]\nroms = "~/roms"\ninboxes = ["~/inbox"]\n'
    loaded = load(write(tmp_path, text))
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
    config.check_library(load(write(tmp_path, valid_text(tmp_path))))


def test_check_library_missing_roms(tmp_path: Path) -> None:
    loaded = load(write(tmp_path, valid_text(tmp_path)))
    with pytest.raises(config.ConfigError, match=r"not a directory.*NAS share mounted"):
        config.check_library(loaded)


def test_check_library_missing_inbox(tmp_path: Path) -> None:
    (tmp_path / "roms").mkdir()
    loaded = load(write(tmp_path, valid_text(tmp_path)))
    with pytest.raises(config.ConfigError, match=r"inbox: not a directory"):
        config.check_library(loaded)


def test_relative_path_rejected(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace(str(tmp_path / "roms"), "roms")
    with pytest.raises(config.ConfigError, match=r"library\.roms 'roms' is not absolute"):
        load(write(tmp_path, text))


def test_unknown_user_home_rejected(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace(str(tmp_path / "roms"), "~no-such-user-xyz/roms")
    with pytest.raises(config.ConfigError, match=r"library\.roms"):
        load(write(tmp_path, text))


def test_empty_list_item_rejected(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + 'regions = [""]\n'
    with pytest.raises(config.ConfigError, match="non-empty strings"):
        load(write(tmp_path, text))


def test_non_utf8_file_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(config.ConfigError, match="cannot read the file"):
        load(path)


def no_dat_text(tmp_path: Path, slug: str = "nes") -> str:
    return valid_text(tmp_path).split("[platforms.nes]")[0] + f"[platforms.{slug}]\n"


def test_dat_defaults_from_registry(tmp_path: Path) -> None:
    platform = load(write(tmp_path, no_dat_text(tmp_path))).platforms["nes"]
    assert platform.dat == "no-intro/Nintendo - Nintendo Entertainment System"


def test_dat_explicit_wins(tmp_path: Path) -> None:
    text = no_dat_text(tmp_path) + 'dat = "redump/Other"\n'
    assert load(write(tmp_path, text)).platforms["nes"].dat == "redump/Other"


def test_unknown_platform_without_dat(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError) as error:
        load(write(tmp_path, no_dat_text(tmp_path, "bogus")))
    message = str(error.value)
    assert "'bogus'" in message
    assert "atari2600, " in message
    assert message.endswith("; or set dat.")


def test_unknown_platform_with_dat(tmp_path: Path) -> None:
    text = no_dat_text(tmp_path, "bogus") + 'dat = "no-intro/Some - Thing"\n'
    assert load(write(tmp_path, text)).platforms["bogus"].dat == "no-intro/Some - Thing"


@pytest.mark.parametrize("dat", ["nes", "other/Name", "no-intro/", "No-Intro/Name"])
def test_dat_shape_rejected(tmp_path: Path, dat: str) -> None:
    text = no_dat_text(tmp_path) + f'dat = "{dat}"\n'
    with pytest.raises(config.ConfigError, match=r"must look like <no-intro\|redump>/<name>"):
        load(write(tmp_path, text))


def test_lowercase_code_rejected(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + 'regions = ["usa"]\n'
    with pytest.raises(config.ConfigError, match=r"unknown code 'usa'. Use upper case.*WORLD"):
        load(write(tmp_path, text))


def test_unknown_language_rejected(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + 'languages = ["XX"]\n'
    with pytest.raises(config.ConfigError, match=r"unknown code 'XX'.*Allowed: DA, DE"):
        load(write(tmp_path, text))


def test_data_dir_env_first() -> None:
    env = {config.DATA_ENV: "/x/data", "XDG_DATA_HOME": "/y"}
    assert config.data_dir(env) == Path("/x/data")


def test_data_dir_xdg() -> None:
    assert config.data_dir({"XDG_DATA_HOME": "/y"}) == Path("/y/rom-scraper")


def test_data_dir_default_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert config.data_dir({}) == tmp_path / ".local" / "share" / "rom-scraper"
    assert not (tmp_path / ".local").exists()
