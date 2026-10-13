# Setup

## Requirements

- Python 3.11+
- Node.js 22.22+ with `npx`, or [igir](https://igir.io) on `PATH`. rom-scraper runs
  `igir@5.7.2` through `npx` when `igir` is not on `PATH`.

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
regions = ["USA", "WORLD"]
languages = ["EN"]

[platforms.custom-system]
dat = "no-intro/Some - Custom System"
```

| Key | Required | Meaning |
| --- | --- | --- |
| `library.roms` | yes | RomM library roms directory. Games for `<slug>` live in `<roms>/<slug>/`. |
| `library.inboxes` | yes | One or more mixed-platform directories where new files arrive. |
| `platforms.<slug>.dat` | no | DAT name, `<no-intro or redump>/<name>`. Omit it for platforms known to rom-scraper. |
| `platforms.<slug>.regions` | no | Wanted regions, igir codes. Default `["USA", "WORLD"]`. |
| `platforms.<slug>.languages` | no | Wanted languages, igir codes. Default `["EN"]`. |

Codes are upper case.

- Regions: ARG ASI AUS BEL BRA CAN CHN DAN EUR FRA FYN GER GRE HK HOL ITA JPN KOR MEX NOR
  NZ POR RUS SPA SWE TAI UK UNK USA WORLD
- Languages: DA DE EL EN ES FI FR IT JA KO NL NO PT RU SV ZH

Each platform wants one release per game (igir `--single`): the preferred region among the
listed regions and languages.

## Data directory

DATs, the igir hash cache, and scan results live in the first of these:

1. `$ROM_SCRAPER_DATA`
2. `$XDG_DATA_HOME/rom-scraper` (default `~/.local/share/rom-scraper`)

The directory is created on first use.

## Verify

```sh
rom-scraper config
```

It prints the resolved config file, data directory, library paths, and platforms. If a path
is not a directory, mount the share and run it again.

## dats update

```sh
rom-scraper dats update [PLATFORM...]
```

Downloads the DAT of each configured platform (all by default) from libretro-database. Prints
`<platform> <version> (updated|unchanged)` per DAT. Run it before the first scan and
whenever you want new releases to show up as missing.

## scan

```sh
rom-scraper scan [PLATFORM...]
```

Hashes the files in `<library.roms>/<slug>` and in every inbox, and matches them to the DAT.
The first scan of a large library is slow; later scans reuse the hash cache.

- have: matched in the library.
- inbox: matched in an inbox only.
- missing: wanted but in neither.
- unmatched: library files that match no DAT entry.

## status

```sh
rom-scraper status
```

Prints one row per configured platform: `wanted` is have + inbox + missing, `done` is
have as a percent of wanted. Platforms never scanned show `-`.

## missing

```sh
rom-scraper missing PLATFORM [--links]
```

Prints one missing game per line. `--links` appends a tab and a Vimm's Lair search URL for
platforms Vimm's Lair carries.
