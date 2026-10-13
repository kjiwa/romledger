# Troubleshooting

Errors print as `rom-scraper: error: <message>` and exit with status 2.

## `config file not found`

Cause: no file at the path. Fix: pass `--config`, set `ROM_SCRAPER_CONFIG`, or create the
file from the example in the message.

## `not a directory. Is the NAS share mounted?`

Cause: `library.roms` or an inbox does not exist, usually because the share is not mounted.
Fix: mount it, or correct the path in the config file.

## `unknown platform 'X'. Use one of: ...; or set dat.`

Symptom: `[platforms.X]` has no `dat` and X is not a known RomM slug. Cause: typo or an
unsupported platform. Fix: use a listed slug, or set `dat = "<no-intro or redump>/<name>"`.

## `platforms.X.dat 'Y' must look like <no-intro|redump>/<name>`

Cause: the DAT name has no set prefix. Fix: write `no-intro/<name>` or `redump/<name>`.

## `platforms.X.regions has unknown code 'Y'`

Cause: not an igir region code, or lower case. Fix: use an upper-case code from the list in
the message.

## `platforms.X.languages has unknown code 'Y'`

Cause: not an igir language code, or lower case. Fix: use an upper-case code from the list
in the message.

## `unknown platform 'X'. Configured platforms: ...`

Symptom: a command argument names a platform that is not in the config. Fix: add
`[platforms.X]` to the config, or use a listed platform.

## `<url>: HTTP 404`

Cause: no such DAT in libretro-database. Fix: correct `platforms.<slug>.dat`; names are
case-sensitive file names under `metadat/no-intro` and `metadat/redump`.

## `<url>: request failed (...)`

Cause: no network, a blocked host, or a timeout. Fix: check the connection and `HTTPS_PROXY`,
then run `rom-scraper dats update` again.

## `no DAT for X (...). run: rom-scraper dats update`

Cause: `scan` ran before the DAT was downloaded. Fix: run `rom-scraper dats update`.

## `X has not been scanned. run: rom-scraper scan`

Cause: `missing X` ran before the first scan. Fix: run `rom-scraper scan X`.

## `igir not found and Node.js 22.22+ (with npx) is required to run it`

Cause: neither `igir` nor `npx` is on `PATH`. Fix: install Node.js 22.22 or newer, or put
igir on `PATH`.

## `igir exited with status N`

Cause: igir failed; the last 20 lines of its output follow the message. Fix: read them. Common
causes are an unreadable directory, an old Node.js, or no network for the first `npx` download.

## `igir finished without writing a report` or `igir report lacks columns`

Cause: igir exited cleanly but wrote no CSV or a different format, usually a newer or older
igir on `PATH`. Fix: remove it from `PATH` so rom-scraper uses its pinned version, or run
igir by hand to see why.

## `cannot run igir: ...`

Cause: the `igir` or `npx` on `PATH` exists but cannot be executed. Fix: check its
permissions or reinstall it.

## `platforms.X.regions is empty`

Cause: `regions` or `languages` is `[]`, which would filter out every game. Fix: list at least
one code or remove the key to use the default.

## `ROM_SCRAPER_DATA ... is not absolute`

Cause: a relative data directory depends on the working directory, so `scan` and `status`
would disagree. Fix: set it to a full path.
