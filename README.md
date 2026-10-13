# rom-scraper

Track which retro games you have and which are missing, verified against No-Intro and Redump DATs.

## Status

Works today: load and validate a config file (`rom-scraper config`).

Planned:

- Catalog and status from DATs
- Import from inbox into a RomM layout
- Automatic downloads from supported sources

## How it fits

- [igir](https://igir.io) matches files to DATs and moves them into place.
- [RomM](https://romm.app) is the library, play, and metadata layer.
- rom-scraper decides what you have and what is missing.

## Install

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
dat = "no-intro/Nintendo - Nintendo Entertainment System"
```

Check it:

```sh
rom-scraper config
```

See [docs/setup.md](docs/setup.md) for all options.
