# Changelog

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
