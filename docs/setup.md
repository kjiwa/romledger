# Setup

## Requirements

- Python 3.11+
- Node.js 22.22+ with `npx`, or [igir](https://igir.io) on `PATH`. romledger runs
  igir through `npx` when `igir` is not on `PATH`.

## Config file

`romledger init` writes this file for you. It prompts for the ROM folder and whether to add
`~/Downloads/romledger` as a second inbox (for the [browser extension](extension.md)), then creates
`<roms>/library` and `<roms>/inbox`. It never overwrites an existing file unless you pass
`--force`. Without a terminal it uses `--roms DIR`, default `~/roms`.

The library and the inboxes are all you have to configure. romledger knows every platform that
`romledger platforms` lists and downloads a platform's DAT the first time it needs it, so a ROM for
any of them is imported and its platform shows up in `status` as soon as it holds a game.

The reference for editing by hand follows.

romledger reads the first of these:

1. `--config FILE`
2. `$ROMLEDGER_CONFIG`
3. `$XDG_CONFIG_HOME/romledger/config.toml` (default `~/.config/romledger/config.toml`)

Unknown keys and wrong types are errors. Paths must be absolute; `~` is expanded.

```toml
[library]
roms = "~/roms/library"
inboxes = ["~/roms/inbox"]

# Optional: what every platform wants. These are the defaults.
[wanted]
regions = ["USA", "WORLD"]
languages = ["EN"]
include = []

# Optional: change any of those three keys for one platform.
[platforms.nes]
include = ["unlicensed"]

[hooks]
after_import = [["touch", "/path/to/roms/.imported"]]

[network]
proxy = "socks5h://proxy.example:1080"
```

| Key | Required | Meaning |
| --- | --- | --- |
| `library.roms` | yes | Library directory. Games for `<slug>` live in `<roms>/<slug>/`. |
| `library.inboxes` | yes | One or more mixed-platform directories where new files arrive. |
| `wanted.regions` | no | Wanted regions, igir codes, best first. Default `["USA", "WORLD"]`. |
| `wanted.languages` | no | Wanted languages, igir codes, best first. Default `["EN"]`. |
| `wanted.include` | no | Categories of release to want that are left out by default: `unlicensed`, `aftermarket`, `prerelease`, `programs`, `bad`. Default none. |
| `platforms.<slug>.regions`, `.languages`, `.include` | no | The same keys for one platform, replacing the `wanted` value. `romledger platforms` lists the slugs. |
| `network.proxy` | no | Proxy URL for every request. Schemes: `http`, `https`, `socks5`, `socks5h`. |
| `hooks.after_import` | no | Commands to run after `import` moved at least one file. Each is an argument list, run without a shell. Default none. |

Codes are upper case.

- Regions: ARG ASI AUS BEL BRA CAN CHN DAN EUR FRA FYN GER GRE HK HOL ITA JPN KOR MEX NOR
  NZ POR RUS SPA SWE TAI UK UNK USA WORLD
- Languages: DA DE EL EN ES FI FR IT JA KO NL NO PT RU SV ZH

Proxies may also come from the `HTTPS_PROXY` or `ALL_PROXY` environment variables; `network.proxy`
wins when both are set. If the proxy URL has a user name but no password, romledger asks for the
password on a terminal. It never prints the password, and shows proxy URLs as `scheme://***@host`.

## What counts as wanted

Each platform wants one release per title. romledger groups the DAT's games by title, drops
the categories you did not `include`, keeps the games whose region and language you listed, and
prefers the release with the fewest extra tags (such as `Evercade` or `Collection`), then the
earliest region and language in your lists, then the newest revision. A title is had when any
wanted release of it is. The categories, by a word in a tag of the game name or of any of its
ROM names (so `Possible Proto`, `Tech Demo` and `Music Program` count):

- `unlicensed`: `Unl`, `Pirate`
- `aftermarket`: `Aftermarket`, `Homebrew`
- `prerelease`: `Proto`, `Beta`, `Demo`, `Sample`, `Kiosk`, `Debug`
- `programs`: `Program`, `Test Program`, `Enhancement Chip`
- `bad`: `[b]` bad dumps

A game with no language tag is taken to speak its region's language.

Run `romledger platforms` to see the platform slugs, their DATs and the sources that carry them.
Set `regions`, `languages` and `include` for every platform under `[wanted]`, or per platform (see
[Config file](#config-file)).

## Where files go

`import` files each inbox game that matches a wanted release into `<library.roms>/<slug>/`,
named after its DAT entry (`<DAT game name>.<ext>`), whatever it was called before. Matching is
by content hash, so names and folders in the inbox do not matter. A zip is matched by its ROM,
which is extracted and filed as `<DAT game name>.<ext>`. igir keeps a zip that holds extra files,
so the zip is set aside in `<inbox>/extracted/`.

Nothing is ever deleted. Files that are not filed move into a folder inside their inbox, keeping
their relative path:

- `<inbox>/extracted/`: a file whose game was filed from it during this import, kept by igir
  because it holds other files.
- `<inbox>/duplicates/`: matched a wanted DAT entry the library already has.
- `<inbox>/unwanted/`: a valid dump that is not wanted: another region or language, or a category
  you did not `include`.
- `<inbox>/unmatched/`: matched no DAT entry, so it is unknown or damaged.

A name collision there gets `.1`, `.2`, ... before the extension. To change what is wanted, edit
`regions`, `languages` or `include`, then move files back out of `unwanted/` into the inbox.

## Data directory

DATs, the igir hash cache, and scan results live in the first of these:

1. `$ROMLEDGER_DATA`
2. `$XDG_DATA_HOME/romledger` (default `~/.local/share/romledger`)

The directory is created on first use.

## Output and exit status

Result lines start with a verb (`moved`, `fetched`, `updated`, `failed`, ...) so they read the same
in every command and are easy to `grep`. Errors and warnings go to stderr as
`romledger: error: ...` and `romledger: warning: ...`; each says what to do. Progress lines
(`scanning snes ...`, `downloading the nes DAT ...`) appear only when stderr is a terminal, so cron
logs and pipes stay quiet.

Color is used only on a terminal: bold table headers, a done percentage that is green, yellow or
red, and colored verbs and error labels. Set `NO_COLOR` to turn it off, or `FORCE_COLOR` to keep
it when piping. `TERM=dumb` also turns it off. Tables fit the terminal width (`$COLUMNS`) and are
never cut when piped.

| Status | Meaning |
| --- | --- |
| 0 | Done. |
| 1 | Something failed but the rest completed: a download, an `after_import` hook, a site layout, or a broken browser host. |
| 2 | A usage or configuration error. Nothing was changed. |
| 130 | Interrupted while prompting. |

`romledger` with no command, and `romledger --help`, list the commands and a typical order for
using them. A mistyped platform suggests the nearest match, and so does a mistyped command on
Python 3.14 and later.

## Verify

```sh
romledger config
```

It prints the resolved config file, data directory, library paths, what is wanted (plus any platform
that differs), and the proxy with credentials hidden. If a path is not a directory, mount the drive
or share and run it again.

## dats update

```sh
romledger dats update [PLATFORM...]
```

Downloads the DAT of each platform (all by default) from libretro-database. Prints
`updated <platform> <version>` or `unchanged <platform> <version>` per DAT. `scan` and `import` download the DATs they
lack on their own, so run this only to pick up new releases and show them as missing.

## scan

```sh
romledger scan [PLATFORM...]
```

Hashes the files in `<library.roms>/<slug>` and in every inbox, and matches them to the DATs, for
every platform unless you name some. It downloads the DATs it lacks. The first scan of a large
library is slow; later scans reuse the hash cache. Counts are per wanted title (see [What counts as
wanted](#what-counts-as-wanted)).

- have: any wanted release of the title is in the library.
- inbox: a wanted release is in an inbox only.
- missing: wanted but in neither. Listed by the preferred release.
- unmatched: library files that match no DAT entry.

Files under `<inbox>/unmatched/`, `<inbox>/unwanted/`, `<inbox>/duplicates/` and
`<inbox>/extracted/` are ignored, as are AppleDouble (`._*`), `.DS_Store`, and partial downloads
(`*.part`, `*.crdownload`, `*.download`).

## status

```sh
romledger status [--all]
```

Prints one row per platform that holds at least one game, in the library or an inbox: `wanted` is
have + inbox + missing, `done` is have as a percent of wanted. A footer counts the platforms left
out. `--all` lists every platform; those never scanned show `-`.

## missing

```sh
romledger missing PLATFORM [--links]
```

Prints one missing game per line. `--links` appends a tab and the Vimm's Lair search URL, for the
platforms Vimm's Lair carries.

## fetch

```sh
romledger fetch [PLATFORM...] [--limit N] [--dry-run] [--no-import] [--source NAME]
```

Downloads the games `missing` lists, one at a time, into the first inbox, for the platforms you
name or, by default, every platform that has games and a source that can be fetched from the
command line. For each game it asks every such source that carries the platform, in order, and
takes the first match. `romledger platforms` lists the sources of each platform; see
[sources.md](sources.md) for what each can do. A download is written
as `<name>.part`, resumed if it was interrupted, checked against the size the server announced (and
the checksum, where the source lists one), then renamed. Then it runs `import`, unless
`--no-import`.

Output per game is `fetched <game> (<source>)`, `not found <game>`, `skipped <game>: <path> ...` or
`failed <game>: <reason>`, then a summary line. A failed game does not stop the others. A game is
skipped when the file a source would send already sits in `<inbox>/unmatched/`, `unwanted/` or
`duplicates/` from an earlier import; delete that file to try again.

- `--limit N`: stop after N games in all.
- `--dry-run`: look games up and print `would fetch <game> (<source>)`; download and import nothing.
  ConsoleRoms is asked for listing and download pages.
- `--source NAME`: use only that source. Vimm's Lair cannot be fetched from the command line.

Run `scan` first. Requests are spaced politely: ConsoleRoms at least 1 second apart (more if its
robots.txt asks). A source whose robots.txt disallows a URL is
skipped for the run. Exit status is 0, 1 if any game failed or a site's layout changed (or an
`after_import` hook failed), or 2 for errors.

## import

```sh
romledger import [--dry-run]
```

Files the inbox into the library; see [Where files go](#where-files-go). Only wanted releases are
filed. It downloads any DAT it lacks first. Afterwards it rescans the platforms that received files
and runs `hooks.after_import`. An inbox that igir empties is recreated.

Output lists `moved <slug> <n>`, `extracted <n>`, `duplicates <n>`, `unwanted <n>` and
`unmatched <n>`; an inbox with nothing to do prints `inbox is empty`.

`--dry-run` changes nothing. It prints what would be filed and the unwanted and unmatched files.
It cannot tell duplicates from new games, so its counts include games the library already has.

Exit status is 0, 1 if an `after_import` hook failed (everything else still completed), or 2 for
errors.

Partial downloads are skipped until the browser renames them. `--watch` imports on its own; see
below.

If another import is running, `import` waits for it to finish. A lock file in the data directory
keeps imports from the command line, `--watch` and the browser extension from overlapping.

## import --watch

```sh
romledger import --watch
```

Keeps running and imports on its own. Every 5 seconds it checks all inboxes, skipping `unmatched`,
`unwanted`, `duplicates` and `extracted` and files that are still downloading (`.part`,
`.crdownload`, `.download`, `._*`, `.DS_Store`). When files are waiting and none changed size or
modification time over the last two checks, it runs an import and prints its output, as `import`
does. If the import fails or leaves files behind, those files are not retried; add or change a
file to try again. It reads the config file on every check, so edits and a remounted library take
effect without a restart. Stop it with Ctrl-C. It cannot be combined with `--dry-run`.

## extension

```sh
romledger extension install
romledger extension uninstall
romledger extension status
```

The browser extension talks to romledger through a small program the browser starts itself, so
there is no server, port or password to set up. `install` writes a launcher into the data
directory and tells each browser it finds (Chrome, Chromium, Brave, Edge and Firefox) where it
is, and which extension may use it.
It records the config file path in effect, so pass `--config` before `install` if yours is not in
the default place. Run it again after you move the config or reinstall romledger. `uninstall`
removes what `install` wrote. `status` lists each browser as `ready`, `not installed`, `not found`,
`stale` (it points at another launcher) or `broken`, and for a ready one starts the launcher and
checks that it answers; the exit status is 1 if any is stale or broken.

The extension can ask for exactly three things: the list of platforms with their counts, the state
of a game by hash or name, and an import after a download finished in an inbox. Windows is not
supported. See [extension.md](extension.md).
