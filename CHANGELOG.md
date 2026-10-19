# Changelog

## Unreleased

- `Enhancement Chip` dumps (the SNES DSP, CX4, ST and Super Game Boy firmware that accurate
  emulators load) are wanted by default again; they are no longer in `programs`.

## 0.6.0

romledger needs only the library and the inbox in its config now, and the command line is its only
interface.

- Every platform romledger knows (`romledger platforms`) is tracked. `import` and `scan` download
  the DATs they lack, and `status` lists a platform once it holds a game; `status --all` lists
  every platform. `init --platform` and `dats index` are gone.
- Set what is wanted once under `[wanted]` (`regions`, `languages`, `include`) and override it for
  one platform under `[platforms.<slug>]`. The `dat`, `sources` and `archive_item` keys were
  removed; the error says to delete them.
- `romledger platforms` is a table of platform, name, DAT set and sources that fits the terminal
  width and is never cut when piped.
- Prototypes, demos and programs are excluded by any word of a tag, not only the first: `Possible
  Proto`, `Auto Demo`, `Tech Demo`, `Music Program`, `Jitsuen-you Sample` and a comma-joined
  `Kiosk, GameCube` no longer count as wanted, and `Enhancement Chip` dumps are programs.
- Sources are modeled by what each can do: Vimm's Lair in the browser (matched by hash), ConsoleRoms
  from `romledger fetch` (matched by title). `fetch` needs no config, defaults to the platforms
  that have games, and takes `--source`. CoolROM, the Internet Archive and emu-land are no longer
  sources, and `missing --links` prints the Vimm's Lair search link only.
- `romledger serve`, the dashboard, its API and the Docker image are gone. The extension talks to
  romledger through a native host the browser starts itself: run `romledger extension install`
  once (macOS and Linux; Chrome, Chromium, Brave, Edge, Firefox). It imports each Vimm's Lair
  download as it finishes. `romledger import --watch` imports files you copy in by hand, and a
  lock keeps imports from overlapping.
- The extension supports Vimm's Lair only, behind a site adapter, and has a "Seconds between
  downloads" option (15 to 600, default 15). Its options page no longer asks for a URL or token.
- Output is consistent: result lines start with a verb, errors and warnings say what to do, and
  progress lines appear only on a terminal. Color (bold headers, a colored done percentage, colored
  verbs and error labels) follows `NO_COLOR`, `FORCE_COLOR` and `TERM=dumb`. `romledger` with no
  command shows the help, which lists the usual order of use and the exit statuses; `dats update`
  prints `updated <platform> <version>`.
- The guide to playing what you collect, and the RomM mentions, are gone: romledger does not
  integrate with them.

### Migrating from 0.5

1. In `config.toml`, delete `dat`, `sources` and `archive_item` from every `[platforms.<slug>]`
   table. Empty tables can stay; tables that only set `regions`, `languages` or `include` keep
   working.
2. If you ran `romledger serve`, use `romledger import --watch` for files you copy in, and run
   `romledger extension install` for the browser extension. Reload the extension; it forgets its
   old URL and token. Add `~/Downloads/romledger` to `library.inboxes` if you use the download
   option.
3. If you used the container image, run romledger on the machine with your browser instead; the
   image is no longer published.
4. Scripts that read `dats update` output now see `updated|unchanged <platform> <version>`.

## 0.5.1

- The "Download N missing" queue starts each download from the Vimm's Lair page, as the Download
  button does. Downloads started from the extension's background were rejected with a server error.
- The queue starts games at least 15 seconds apart and stops at the first failed download or when
  Vimm's Lair says to slow down.

## 0.5.0

- The extension marks games on every Vimm's Lair letter page (`/vault/<system>/<letter>`), not only
  the `number` page.
- A Vimm's Lair list page gets a "Download N missing" box. With the download option on, it
  downloads each missing game one at a time into `Downloads/romledger` and pauses when Vimm's Lair
  withholds the download until you pass its check. The option is now worded "Download from Vimm's
  Lair into Downloads/romledger".
- The options checkbox lines up with its label.

## 0.4.1

- `import` no longer fails partway when igir removes the emptied inbox the command was run from.
  The moved ROMs are now scanned and the set-aside folders filled in.

## 0.4.0

- `fetch` can download from ConsoleRoms. List `consoleroms` in a platform's `sources`; it carries
  about thirty platforms, Nintendo systems included.
- `missing --links` appends an emu-land search URL after the Vimm's Lair one, and the dashboard and
  `/api/platforms` carry it too (`links.emuland`, `sites.emuland`, `sites.consoleroms`). emu-land
  downloads are manual.
- `missing --links` prints tab-separated columns (game, Vimm's Lair, emu-land), with an empty cell
  where a site has no link. Column 2 is still Vimm's Lair.
- The extension marks games on ConsoleRoms and emu-land.
- `platforms.toml` gains ConsoleRoms and emu-land codes.

## 0.3.2

- `import` files a game whose name the DAT repeats in separate blocks, such as `(USA)` and its
  `(Alt)` dump or an NES game and its unheadered `.unh` twin. These were set aside as unwanted
  because igir saw one game that no single file completed.
- `fetch` skips a game whose earlier download is set aside in `<inbox>/unmatched`, `unwanted` or
  `duplicates`, and prints `skipped <game>` and a `skipped` count, instead of downloading it again.
- The database schema is v4. The DAT index rebuilds on first use; scans are kept.

## 0.3.1

- `import` extracts ROMs from zips and files them under their DAT names. Zips whose ROM name differs
  from the DAT, such as CoolROM downloads, were set aside as duplicates and never imported. A zip
  igir keeps because it holds extra files moves to `<inbox>/extracted`.

## 0.3.0

- `romledger init` writes a starter config and creates the library and inbox folders;
  `romledger platforms` lists the platform slugs. The missing-config error points at `init`.
- The wanted library is computed in romledger: non-retail releases are left out (a platform's
  `include` adds categories back) and one preferred release is kept per title by tags, region,
  language and revision. `import` files only wanted games and sets valid but unwanted dumps aside
  in `<inbox>/unwanted`.
- The database schema is v3 and resets existing scans; run `scan` again after upgrading.
- `serve` imports inbox files once they stop changing; `--no-auto-import` turns it off.
- The extension can save Vimm's Lair downloads to `Downloads/romledger` through an optional
  `downloads` permission.
- An ambiguous name lookup returns every candidate, narrowed by region and tags; the extension
  shows the best state.
- Fix inboxes that igir empties, zips that hold extra files beside a ROM, and a slow title-tag
  match. The Internet Archive search link is removed.

## 0.2.0

- Install from PyPI: `uv tool install romledger` or `pipx install romledger`.
- The container image is published to `ghcr.io/kjiwa/romledger` for `linux/amd64` and
  `linux/arm64`, and the Compose example pulls it.
- Each release attaches `romledger-extension-<version>.zip` for loading the extension unpacked.
- The extension options page starts with `http://127.0.0.1:8730`.
- Documentation and examples no longer assume a particular host, a network share or RomM; the
  contributor material moved to `CONTRIBUTING.md`.

## 0.1.0

First release.

- `dats`, `scan`, `status` and `missing` compare a ROM library against No-Intro and Redump DATs
  through igir and report what each platform has and lacks.
- `import` files downloads from an inbox into the `roms/<platform>/` library layout, which RomM also reads.
- `fetch` downloads missing games from CoolROM and the Internet Archive.
- `serve` runs a local dashboard and JSON API with a DAT hash index and a lookup endpoint.
- `canary` checks that the supported sites and the igir pin still match; CI runs it weekly.
- A Dockerfile and Compose example, with deployment docs.
- A browser extension that marks games you have, are missing or have waiting in the inbox on Vimm's
  Lair, CoolROM and the Internet Archive.
- A guide to playing the library on common devices and emulators.
