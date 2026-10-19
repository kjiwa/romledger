# romledger

Track which retro games you have and which are missing, verified against No-Intro and Redump DATs.
It runs on one computer: point it at a folder of ROMs and it reports, per platform, what is there
and what is not.

## How it works

1. Run `romledger init` once. It creates the config file, `library/` and `inbox/`.
2. Download a game: use the [browser extension](https://github.com/kjiwa/romledger/blob/master/docs/extension.md)
   on Vimm's Lair, run `romledger fetch`, or copy files into the inbox yourself. The files land in
   the inbox.
3. Import. Run `romledger import`, or `romledger import --watch` to keep it running; the extension
   imports each Vimm's Lair download as it finishes. Each file is checked against the DAT, renamed
   to its DAT name and filed under `library/<platform>/`.
4. Files that do not fit are set aside inside the inbox, never deleted: `inbox/unmatched/` (not in
   any DAT), `inbox/unwanted/` (a valid dump you did not ask for) and `inbox/duplicates/` (you
   already have it).

The inbox is a plain folder. Copy files into it yourself, zipped or not, and the next import
processes whatever is there. A zip is matched by the ROM inside it and the ROM is extracted, so you
do not unzip it.

![A terminal running romledger status, which lists wanted, have, inbox, missing and unmatched counts per platform, then romledger missing snes, which lists missing games.](https://raw.githubusercontent.com/kjiwa/romledger/master/docs/images/demo.gif)

## How it fits

- [igir](https://igir.io) matches files to DATs and moves them into place.
- romledger decides what you have and what is missing.
- The library is plain folders, `library/<platform>/`, named after each game's DAT entry.

## Install

Requires Python 3.11+ and Node.js 22.22+ (romledger runs [igir](https://igir.io) through `npx`).

```sh
uv tool install romledger
```

or, with [pipx](https://pipx.pypa.io):

```sh
pipx install romledger
```

## Configure

```sh
romledger init
```

It asks for a ROM folder, creates `<roms>/library` and `<roms>/inbox`, and writes
`~/.config/romledger/config.toml`. Nothing else needs configuring: romledger knows the platforms
`romledger platforms` lists and downloads their DATs when it first needs them. Without a terminal,
pass `romledger init --roms ~/roms`.

Then put ROMs in the inbox, import them and see where you stand:

```sh
romledger import
romledger status
```

To mark and download games on Vimm's Lair from your browser, run `romledger extension install` and
follow [docs/extension.md](https://github.com/kjiwa/romledger/blob/master/docs/extension.md).
`romledger --help` lists every command.

See [docs/setup.md](https://github.com/kjiwa/romledger/blob/master/docs/setup.md) for all options,
[docs/extension.md](https://github.com/kjiwa/romledger/blob/master/docs/extension.md) for the browser extension,
[docs/sources.md](https://github.com/kjiwa/romledger/blob/master/docs/sources.md) for download sources and
[docs/troubleshooting.md](https://github.com/kjiwa/romledger/blob/master/docs/troubleshooting.md) for error messages.

To work on romledger, see [CONTRIBUTING.md](https://github.com/kjiwa/romledger/blob/master/CONTRIBUTING.md).
