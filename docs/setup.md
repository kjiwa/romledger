# Setup

## Config file

rom-scraper reads the first of these:

1. `--config FILE`
2. `$ROM_SCRAPER_CONFIG`
3. `$XDG_CONFIG_HOME/rom-scraper/config.toml` (default `~/.config/rom-scraper/config.toml`)

Unknown keys and wrong types are errors. Paths must be absolute; `~` is expanded.

```toml
[library]
roms = "/mnt/roms/roms"
inboxes = ["/mnt/roms/inbox"]

[platforms.nes]
dat = "no-intro/Nintendo - Nintendo Entertainment System"
regions = ["USA", "World"]
languages = ["En"]
```

| Key | Required | Meaning |
| --- | --- | --- |
| `library.roms` | yes | RomM library roms directory. |
| `library.inboxes` | yes | One or more directories where new files arrive. |
| `platforms.<slug>.dat` | yes | DAT name, `<set>/<name>`. |
| `platforms.<slug>.regions` | no | Wanted regions. Default `["USA", "World"]`. |
| `platforms.<slug>.languages` | no | Wanted languages. Default `["En"]`. |

## Verify

```sh
rom-scraper config
```

It prints the resolved config file, library paths, and platforms. If a path is
not a directory, mount the share and run it again.
