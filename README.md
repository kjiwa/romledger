# rom-scraper

Track which retro games you have and which are missing, verified against No-Intro and Redump DATs.

## Status

Works today:

- Validate a config file (`rom-scraper config`)
- Download No-Intro and Redump DATs (`rom-scraper dats update`)
- Match your library and inboxes to the DATs (`rom-scraper scan`)
- Show progress per platform (`rom-scraper status`)
- List missing games, with Vimm's Lair search links (`rom-scraper missing nes --links`)
- Import from the inboxes into a RomM layout (`rom-scraper import`)

Planned:

- Automatic downloads from supported sources

## How it fits

- [igir](https://igir.io) matches files to DATs and moves them into place.
- [RomM](https://romm.app) is the library, play, and metadata layer.
- rom-scraper decides what you have and what is missing.

## Install

Requires Python 3.11+ and Node.js 22.22+ (rom-scraper runs [igir](https://igir.io) through `npx`).

```sh
uv tool install git+ssh://git@github.com/kjiwa/rom-scraper
```

## Configure

Create `~/.config/rom-scraper/config.toml`:

```toml
[library]
roms = "/mnt/roms/roms"
inboxes = ["/mnt/roms/inbox"]

[platforms.nes]
```

Platform names are RomM slugs. `dat` is filled in for known platforms.

Check it, then fetch DATs and scan:

```sh
rom-scraper config
rom-scraper dats update
rom-scraper scan
rom-scraper status
```

See [docs/setup.md](docs/setup.md) for all options and
[docs/troubleshooting.md](docs/troubleshooting.md) for error messages.
