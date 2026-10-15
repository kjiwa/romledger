# Changelog

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
