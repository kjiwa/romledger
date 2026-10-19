from pathlib import Path

import pytest

from romledger import config, registry

VALID = """\
[library]
roms = "{roms}"
inboxes = ["{inbox}"]

[platforms.nes]
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
    assert set(loaded.platforms) == set(registry.load())


def test_a_config_with_only_a_library_is_valid(tmp_path: Path) -> None:
    text = valid_text(tmp_path).split("[platforms.nes]")[0]
    loaded = load(write(tmp_path, text))
    assert loaded.platforms["snes"] == config.Platform(
        dat=registry.load()["snes"].dat, coolrom=None, consoleroms="snes"
    )
    assert loaded.wanted == config.Wanted()


def test_platform_defaults(tmp_path: Path) -> None:
    platform = load(write(tmp_path, valid_text(tmp_path))).platforms["nes"]
    assert platform.regions == ("USA", "WORLD")
    assert platform.languages == ("EN",)
    assert platform.include == ()


def test_include_parsed_and_deduplicated(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + 'include = ["unlicensed", "bad", "unlicensed"]\n'
    assert load(write(tmp_path, text)).platforms["nes"].include == ("unlicensed", "bad")


def test_empty_include_is_allowed(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + "include = []\n"
    assert load(write(tmp_path, text)).platforms["nes"].include == ()


def test_unknown_include_category_rejected(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + 'include = ["homebrew"]\n'
    with pytest.raises(
        config.ConfigError,
        match=r"platforms\.nes\.include has unknown category 'homebrew'.*Allowed: unlicensed, ",
    ):
        load(write(tmp_path, text))


def test_include_must_be_a_list_of_strings(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + 'include = "bad"\n'
    with pytest.raises(config.ConfigError, match=r"platforms\.nes\.include must be a list"):
        load(write(tmp_path, text))


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
    with pytest.raises(config.ConfigError, match="unknown key bogus"):
        load(write(tmp_path, "bogus = 1\n" + valid_text(tmp_path)))


def test_hooks_default_empty(tmp_path: Path) -> None:
    assert load(write(tmp_path, valid_text(tmp_path))).hooks.after_import == ()


def test_hooks_parsed(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + '\n[hooks]\nafter_import = [["touch", "/x"], ["true"]]\n'
    assert load(write(tmp_path, text)).hooks.after_import == (("touch", "/x"), ("true",))


def test_unknown_hooks_key(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match=r"unknown key hooks\.before_import"):
        load(write(tmp_path, valid_text(tmp_path) + "\n[hooks]\nbefore_import = []\n"))


@pytest.mark.parametrize(
    "value", ['"touch x"', '["touch"]', "[[]]", '[[""]]', "[[1]]", '[["a"], "b"]']
)
def test_invalid_hooks(tmp_path: Path, value: str) -> None:
    text = valid_text(tmp_path) + f"\n[hooks]\nafter_import = {value}\n"
    with pytest.raises(config.ConfigError, match=r"hooks\.after_import must be a list of commands"):
        load(write(tmp_path, text))


def test_wrong_type(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace('inboxes = ["', 'inboxes = "').replace('"]', '"')
    with pytest.raises(
        config.ConfigError, match=r"library\.inboxes must be a list of non-empty strings"
    ):
        load(write(tmp_path, text))


def test_wrong_type_string(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace('roms = "', "roms = 5 #")
    with pytest.raises(config.ConfigError, match=r"library\.roms must be a non-empty string"):
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
    target = tmp_path / "romledger" / "config.toml"
    target.parent.mkdir()
    target.write_text("")
    assert config.resolve_path(None, {"XDG_CONFIG_HOME": str(tmp_path)}) == target


def test_resolve_default_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    target = tmp_path / ".config" / "romledger" / "config.toml"
    target.parent.mkdir(parents=True)
    target.write_text("")
    assert config.resolve_path(None, {}) == target


def test_resolve_missing_file(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError) as error:
        config.resolve_path(None, {"XDG_CONFIG_HOME": str(tmp_path)})
    message = str(error.value)
    assert str(tmp_path / "romledger" / "config.toml") in message
    assert "not found" in message
    assert "romledger init" in message


def test_check_library_ok(tmp_path: Path) -> None:
    (tmp_path / "roms").mkdir()
    (tmp_path / "inbox").mkdir()
    config.check_library(load(write(tmp_path, valid_text(tmp_path))))


def test_check_library_missing_roms(tmp_path: Path) -> None:
    loaded = load(write(tmp_path, valid_text(tmp_path)))
    with pytest.raises(config.ConfigError, match=r"not a directory.*drive or share mounted"):
        config.check_library(loaded)


def test_check_library_creates_a_missing_inbox(tmp_path: Path) -> None:
    (tmp_path / "roms").mkdir()
    loaded = load(write(tmp_path, valid_text(tmp_path)))
    config.check_library(loaded)
    assert (tmp_path / "inbox").is_dir()


def test_check_library_unwritable_inbox_parent(tmp_path: Path) -> None:
    (tmp_path / "roms").mkdir()
    loaded = load(write(tmp_path, valid_text(tmp_path)))
    tmp_path.chmod(0o555)
    try:
        with pytest.raises(config.ConfigError, match=r"inbox: cannot create"):
            config.check_library(loaded)
    finally:
        tmp_path.chmod(0o755)


def test_check_library_missing_inbox_parent(tmp_path: Path) -> None:
    (tmp_path / "roms").mkdir()
    text = valid_text(tmp_path).replace(str(tmp_path / "inbox"), str(tmp_path / "gone" / "inbox"))
    loaded = load(write(tmp_path, text))
    with pytest.raises(config.ConfigError, match=r"inbox: not a directory"):
        config.check_library(loaded)
    assert not (tmp_path / "gone").exists()


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


def test_dat_comes_from_the_registry(tmp_path: Path) -> None:
    platform = load(write(tmp_path, valid_text(tmp_path))).platforms["nes"]
    assert platform.dat == "no-intro/Nintendo - Nintendo Entertainment System"


def test_unknown_platform_suggests_the_nearest(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace("platforms.nes", "platforms.snez")
    with pytest.raises(config.ConfigError, match=r"platforms\.snez: unknown platform 'snez'.*snes"):
        load(write(tmp_path, text))


def test_unknown_platform_without_a_near_match(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace("platforms.nes", "platforms.zzzzzz")
    with pytest.raises(config.ConfigError, match=r"Run romledger platforms to list them"):
        load(write(tmp_path, text))


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ('dat = "no-intro/X"', "romledger picks each platform's DAT"),
        ('sources = ["coolrom"]', "fetch uses every source that carries the platform"),
        ('archive_item = "x"', "the Internet Archive is no longer a fetch source"),
    ],
)
def test_removed_platform_keys_say_what_to_do(tmp_path: Path, line: str, reason: str) -> None:
    key = line.split(" ")[0]
    with pytest.raises(
        config.ConfigError, match=rf"platforms\.nes\.{key} was removed in 0.6\. Delete it: {reason}"
    ):
        load(write(tmp_path, valid_text(tmp_path) + line + "\n"))


def test_wanted_sets_the_default_for_every_platform(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace(
        "[platforms.nes]", '[wanted]\nregions = ["EUR"]\ninclude = ["bad"]\n\n[platforms.nes]'
    )
    loaded = load(write(tmp_path, text))
    assert loaded.wanted == config.Wanted(regions=("EUR",), include=("bad",))
    assert loaded.platforms["snes"].regions == ("EUR",)
    assert loaded.platforms["snes"].languages == ("EN",)
    assert loaded.platforms["snes"].include == ("bad",)


def test_a_platform_overrides_wanted_key_by_key(tmp_path: Path) -> None:
    text = valid_text(tmp_path).replace(
        "[platforms.nes]", '[wanted]\nregions = ["EUR"]\n\n[platforms.nes]'
    )
    nes = load(write(tmp_path, text + 'languages = ["FR"]\n')).platforms["nes"]
    assert (nes.regions, nes.languages) == (("EUR",), ("FR",))


def test_unknown_wanted_key(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + '\n[wanted]\nregion = ["USA"]\n'
    with pytest.raises(config.ConfigError, match=r"unknown key wanted\.region"):
        load(write(tmp_path, text))


def test_wanted_errors_name_the_wanted_table(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + '\n[wanted]\nlanguages = ["XX"]\n'
    with pytest.raises(config.ConfigError, match=r"wanted\.languages has unknown code 'XX'"):
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
    assert config.data_dir({"XDG_DATA_HOME": "/y"}) == Path("/y/romledger")


def test_data_dir_default_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert config.data_dir({}) == tmp_path / ".local" / "share" / "romledger"
    assert not (tmp_path / ".local").exists()


def test_data_dir_rejects_relative_env() -> None:
    with pytest.raises(config.ConfigError, match="not absolute"):
        config.data_dir({config.DATA_ENV: "data"})


def test_data_dir_ignores_relative_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert config.data_dir({"XDG_DATA_HOME": "rel"}) == tmp_path / ".local" / "share" / "romledger"


def test_empty_regions_rejected(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + "regions = []\n"
    with pytest.raises(config.ConfigError, match="regions is empty"):
        load(write(tmp_path, text))


def test_site_codes_come_from_the_registry(tmp_path: Path) -> None:
    platforms = load(write(tmp_path, valid_text(tmp_path))).platforms
    assert (platforms["nes"].coolrom, platforms["nes"].consoleroms) == (None, "nes")
    assert (platforms["atari7800"].coolrom, platforms["atari7800"].consoleroms) == (
        "atari7800",
        "atari-7800",
    )


def test_no_network_by_default(tmp_path: Path) -> None:
    assert load(write(tmp_path, valid_text(tmp_path))).network.proxy is None


@pytest.mark.parametrize(
    "proxy",
    ["http://p:3128", "https://p", "socks5://u@p:1080", "socks5h://u:pw@p:1080"],
)
def test_proxy_parsed(tmp_path: Path, proxy: str) -> None:
    text = valid_text(tmp_path) + f'\n[network]\nproxy = "{proxy}"\n'
    assert load(write(tmp_path, text)).network.proxy == proxy


@pytest.mark.parametrize("proxy", ["ftp://p:21", "p:3128", "http://", "socks4://p:1080"])
def test_proxy_scheme_is_validated(tmp_path: Path, proxy: str) -> None:
    text = valid_text(tmp_path) + f'\n[network]\nproxy = "{proxy}"\n'
    with pytest.raises(config.ConfigError, match=r"network\.proxy .* http, https, socks5, socks5h"):
        load(write(tmp_path, text))


def test_proxy_error_does_not_leak_credentials(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + '\n[network]\nproxy = "ftp://alice:hunter2@p:21"\n'
    with pytest.raises(config.ConfigError) as error:
        load(write(tmp_path, text))
    assert "hunter2" not in str(error.value)
    assert "alice" not in str(error.value)


def test_proxy_with_a_bad_port(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + '\n[network]\nproxy = "http://p:notaport"\n'
    with pytest.raises(config.ConfigError, match=r"network\.proxy is not a valid URL"):
        load(write(tmp_path, text))


def test_proxy_must_be_a_string(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + "\n[network]\nproxy = 5\n"
    with pytest.raises(config.ConfigError, match=r"network\.proxy must be a non-empty string"):
        load(write(tmp_path, text))


def test_unknown_network_key(tmp_path: Path) -> None:
    text = valid_text(tmp_path) + "\n[network]\nretries = 3\n"
    with pytest.raises(config.ConfigError, match=r"unknown key network\.retries"):
        load(write(tmp_path, text))


def test_empty_network_table(tmp_path: Path) -> None:
    assert load(write(tmp_path, valid_text(tmp_path) + "\n[network]\n")).network.proxy is None
