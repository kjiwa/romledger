# Setup

## Requirements

- Python 3.11+
- Node.js 22.22+ with `npx`, or [igir](https://igir.io) on `PATH`. romledger runs
  `igir@5.7.2` through `npx` when `igir` is not on `PATH`.

## Config file

romledger reads the first of these:

1. `--config FILE`
2. `$ROMLEDGER_CONFIG`
3. `$XDG_CONFIG_HOME/romledger/config.toml` (default `~/.config/romledger/config.toml`)

Unknown keys and wrong types are errors. Paths must be absolute; `~` is expanded.

```toml
[library]
roms = "/mnt/roms/roms"
inboxes = ["/mnt/roms/inbox"]

[platforms.nes]
regions = ["USA", "WORLD"]
languages = ["EN"]

[platforms.atari7800]
sources = ["coolrom", "internet-archive"]
archive_item = "No-Intro_Atari7800"

[platforms.custom-system]
dat = "no-intro/Some - Custom System"

[hooks]
after_import = [["touch", "/mnt/roms/.imported"]]

[network]
proxy = "socks5h://proxy.example:1080"
```

| Key | Required | Meaning |
| --- | --- | --- |
| `library.roms` | yes | RomM library roms directory. Games for `<slug>` live in `<roms>/<slug>/`. |
| `library.inboxes` | yes | One or more mixed-platform directories where new files arrive. |
| `platforms.<slug>.dat` | no | DAT name, `<no-intro or redump>/<name>`. Omit it for platforms known to romledger. |
| `platforms.<slug>.regions` | no | Wanted regions, igir codes. Default `["USA", "WORLD"]`. |
| `platforms.<slug>.languages` | no | Wanted languages, igir codes. Default `["EN"]`. |
| `platforms.<slug>.sources` | no | Sources `fetch` tries, in order: `coolrom`, `internet-archive`. Default none. `coolrom` needs a platform CoolROM carries. |
| `platforms.<slug>.archive_item` | with `internet-archive` | Internet Archive item that holds `<game name>.zip` files, such as a No-Intro set. |
| `network.proxy` | no | Proxy URL for every request. Schemes: `http`, `https`, `socks5`, `socks5h`. |
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

Proxies may also come from the `HTTPS_PROXY` or `ALL_PROXY` environment variables; `network.proxy`
wins when both are set. If the proxy URL has a user name but no password, romledger asks for the
password on a terminal. It never prints the password, and shows proxy URLs as `scheme://***@host`.

Crawling a site requires the site operator's permission; see [sources.md](sources.md) before you
list a source.

## Data directory

DATs, the igir hash cache, and scan results live in the first of these:

1. `$ROMLEDGER_DATA`
2. `$XDG_DATA_HOME/romledger` (default `~/.local/share/romledger`)

The directory is created on first use.

## Verify

```sh
romledger config
```

It prints the resolved config file, data directory, library paths, platforms with their sources, and
the proxy with credentials hidden. If a path
is not a directory, mount the share and run it again.

## dats update

```sh
romledger dats update [PLATFORM...]
```

Downloads the DAT of each configured platform (all by default) from libretro-database. Prints
`<platform> <version> (updated|unchanged)` per DAT. Run it before the first scan and
whenever you want new releases to show up as missing.

## scan

```sh
romledger scan [PLATFORM...]
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
romledger status
```

Prints one row per configured platform: `wanted` is have + inbox + missing, `done` is
have as a percent of wanted. Platforms never scanned show `-`.

## missing

```sh
romledger missing PLATFORM [--links]
```

Prints one missing game per line. `--links` appends a tab and a Vimm's Lair search URL for
platforms Vimm's Lair carries.

## fetch

```sh
romledger fetch PLATFORM [--limit N] [--dry-run] [--no-import] [--source NAME]
```

Downloads the games `missing` lists, one at a time, into the first inbox. For each game it asks the
platform's `sources` in order and takes the first match. A download is written as `<name>.part`,
resumed if it was interrupted, checked against the size the server announced (and the checksum,
where the source lists one), then renamed. Then it runs `import`, unless `--no-import`.

Output per game is `fetched <game> (<source>)`, `not found <game>`, or `failed <game>: <reason>`,
then a summary line. A failed game does not stop the others.

- `--limit N`: stop after N games.
- `--dry-run`: look games up and print `would fetch <game> (<source>)`; download and import nothing.
  CoolROM is asked for section pages only.
- `--source NAME`: use only that one configured source.

Run `scan` first. Requests are spaced politely: CoolROM at least 10 seconds apart (more if its
robots.txt asks), Internet Archive at least 1 second. A source whose robots.txt disallows a URL is
skipped for the run. Exit status is 0, 1 if any game failed or a site's layout changed (or an
`after_import` hook failed), or 2 for errors.

## import

```sh
romledger import [--dry-run]
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
`romledger import`. Partial downloads are skipped until the browser renames them.

Disc images: igir can read CHD; matching Redump CHDs is unverified.
