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

[hooks]
after_import = [["touch", "/mnt/roms/.imported"]]
```

| Key | Required | Meaning |
| --- | --- | --- |
| `library.roms` | yes | RomM library roms directory. Games for `<slug>` live in `<roms>/<slug>/`. |
| `library.inboxes` | yes | One or more mixed-platform directories where new files arrive. |
| `platforms.<slug>.dat` | no | DAT name, `<no-intro or redump>/<name>`. Omit it for platforms known to rom-scraper. |
| `platforms.<slug>.regions` | no | Wanted regions, igir codes. Default `["USA", "WORLD"]`. |
| `platforms.<slug>.languages` | no | Wanted languages, igir codes. Default `["EN"]`. |
| `hooks.after_import` | no | Commands to run after `import` moved at least one file. Each is an argument list, run without a shell. Default none. |

Codes are upper case.

- Regions: ARG ASI AUS BEL BRA CAN CHN DAN EUR FRA FYN GER GRE HK HOL ITA JPN KOR MEX NOR
  NZ POR RUS SPA SWE TAI UK UNK USA WORLD
- Languages: DA DE EL EN ES FI FR IT JA KO NL NO PT RU SV ZH

RomM's own filesystem watcher or scheduled rescan (`ENABLE_RESCAN_ON_FILESYSTEM_CHANGE`,
`ENABLE_SCHEDULED_RESCAN`) normally makes a hook unnecessary. Whether inotify events arrive over
SMB or NFS is unverified, so prefer the scheduled rescan for a share.

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

Files under `<inbox>/unmatched/` and `<inbox>/duplicates/` are ignored, as are AppleDouble
(`._*`), `.DS_Store`, and partial downloads (`*.part`, `*.crdownload`, `*.download`).

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

## import

```sh
rom-scraper import [--dry-run]
```

Files every inbox game that matches a DAT of a configured platform into
`<library.roms>/<slug>/`, hashing contents, so names and folders in the inbox do not matter.
Import applies no region or language filter. Then it rescans the platforms that received files
and runs `hooks.after_import`.

Nothing is ever deleted. Files that are not moved are relocated inside their inbox, keeping
their relative path:

- `<inbox>/duplicates/`: matched a DAT entry the library already has.
- `<inbox>/unmatched/`: matched no DAT entry.

A name collision there gets `.1`, `.2`, ... before the extension. Output lists
`moved <slug> <n>`, `duplicates <n>`, and `unmatched <n>`; an inbox with nothing to do prints
`inbox is empty`. `--dry-run` prints what would be filed (it cannot tell duplicates from new games, so its counts include games the library already has) and the unmatched files, and changes
nothing; duplicates are only known after filing, so it does not list them.

Exit status is 0, 1 if an `after_import` hook failed (everything else still completed), or 2 for
errors.

Manual downloads from Vimm's Lair: download in a browser into an inbox, then run
`rom-scraper import`. Partial downloads are skipped until the browser renames them.

Disc images: igir can read CHD; matching Redump CHDs is unverified.
