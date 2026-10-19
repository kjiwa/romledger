# Troubleshooting

Errors print as `romledger: error: <message>` and exit with status 2.

## `config file not found`

Cause: no file at the path. Fix: run `romledger init`, or pass `--config` or set
`ROMLEDGER_CONFIG`.

## `not a directory. Is the drive or share mounted?`

Cause: `library.roms` or an inbox does not exist, usually because the drive or share is not mounted.
Fix: mount it, or correct the path in the config file. A missing inbox whose parent directory
exists is created, so this error for an inbox means the parent is missing too.

## A zip sits in `<inbox>/extracted/`

Cause: a download zip held a readme or similar next to the ROM. igir extracts the ROM into the
library but keeps a zip it did not fully use. Fix: none needed; the ROM is filed. Delete the zip
when you no longer want it.

## `platforms.X.regions has unknown code 'Y'`

Cause: not an igir region code, or lower case. Fix: use an upper-case code from the list in
the message.

## `platforms.X.include has unknown category 'Y'`

Cause: `include` lists a name that is not a category. Fix: use one of `unlicensed`,
`aftermarket`, `prerelease`, `programs`, `bad`.

## `platforms.X.languages has unknown code 'Y'`

Cause: not an igir language code, or lower case. Fix: use an upper-case code from the list
in the message.

## `unknown platform 'X'. Nearest: ...`

Symptom: a command argument or a `[platforms.X]` table names a platform romledger does not know.
Cause: a typo, or a platform that is not supported. Fix: use a slug from `romledger platforms`.

## `platforms.X.dat was removed in 0.6. Delete it: ...`

Cause: a config from 0.5 still has `dat`, `sources` or `archive_item` under a platform. Fix: delete
the key. romledger picks each platform's DAT, and `fetch` uses every source that carries the
platform.

## `<url>: HTTP 404`

Cause: libretro-database has no DAT under that name, which means romledger's table is out of date.
Fix: update romledger, or [open an issue](https://github.com/kjiwa/romledger/issues).

## `<url>: request failed (...)`

Cause: no network, a blocked host, or a timeout. Fix: check the connection and `HTTPS_PROXY`,
then run the command again.

## `no DAT could be downloaded (N failed). ...`

Cause: `scan` or `import` found no DAT on disk and could not download any, usually because there is
no network. A platform whose DAT alone fails is skipped with a warning. Fix: check the connection
and `HTTPS_PROXY`, then run the command again.

## `X has not been scanned. run: romledger scan`

Cause: `missing X` ran before the first scan. Fix: run `romledger scan X`.

## `cannot write to <inbox>: ...`

Cause: the inbox is read-only or full. Fix: check the directory's permissions and free space.

## `igir not found and Node.js 22.22+ (with npx) is required to run it`

Cause: neither `igir` nor `npx` is on `PATH`. Fix: install Node.js 22.22 or newer, or put
igir on `PATH`.

## `igir exited with status N`

Cause: igir failed; the last 20 lines of its output follow the message. Fix: read them. Common
causes are an unreadable directory, an old Node.js, or no network for the first `npx` download.

## `igir finished without writing a report` or `igir report lacks columns`

Cause: igir exited cleanly but wrote no CSV or a different format, usually a newer or older
igir on `PATH`. Fix: remove it from `PATH` so romledger uses its pinned version, or run
igir by hand to see why.

## `cannot run igir: ...`

Cause: the `igir` or `npx` on `PATH` exists but cannot be executed. Fix: check its
permissions or reinstall it.

## `platforms.X.regions is empty`

Cause: `regions` or `languages` is `[]`, which would want no game. Fix: list at least
one code or remove the key to use the default.

## `hooks.after_import must be a list of commands`

Cause: the value is not a list of argument lists, or an argument is empty. Fix: write
`after_import = [["touch", "/path/to/roms/.imported"]]`.

## `unknown key hooks.X`

Cause: `[hooks]` supports only `after_import`. Fix: remove the key.

## `warning: <path> is not under any inbox; left in place`

Cause: igir reported a file outside every configured inbox, so `import` will not move it. Fix:
move it by hand, or add its directory to `library.inboxes`.

## `after_import hook failed: <command>: exit status N`

Cause: a hook returned non-zero, or could not start (the message then names the OS error).
The files were already imported and rescanned; `import` exits with status 1. Fix: run the
command by hand. Hooks run only when a file moved, so re-running `import` does not retry it.

## `ROMLEDGER_DATA ... is not absolute`

Cause: a relative data directory depends on the working directory, so `scan` and `status`
would disagree. Fix: set it to a full path.

## `no source can fetch X. Download it by hand into an inbox.`

Cause: no fetch source carries the platform. Fix: download its games in a browser into an inbox;
see [sources.md](sources.md).

## `no source 'X' carries <platform>. Sources for <platform>: ...`

Cause: `--source X` names a source that does not carry the platform. Fix: use one of the listed
names, or leave `--source` out.

## `network.proxy ... must be <scheme>://[user@]host[:port]`

Cause: the proxy URL has an unsupported scheme or no host. Fix: use `http`, `https`, `socks5`, or
`socks5h`. Credentials are hidden in the message.

## `network.proxy is not a valid URL`

Cause: the proxy URL does not parse, usually a non-numeric port. Fix: correct it.

## `unknown key network.X`

Cause: `[network]` supports only `proxy`. Fix: remove the key.

## `--limit: 'X' is not a positive integer`

Cause: `--limit` needs a whole number of at least 1. Fix: pass one, or omit the option.

## `failed <game>: <reason>`

Cause: that game could not be downloaded; `fetch` went on to the next game and exits 1. Fix: read
the reason, then run `fetch` again; interrupted downloads resume. Reasons:

- `<url>: HTTP N`: the site refused or lost the file. Retry later, or download by hand.
- `downloaded N bytes, expected M; removed it`: the transfer was cut short. Retry.
- `md5 does not match the source listing; removed it`: the file was corrupt in transit or changed
  upstream. Retry; if it repeats, download by hand.
- `partial file no longer valid; removed it, run fetch again` and `server resumed at the wrong
  offset; removed the partial file`: the server changed the file between attempts. Run `fetch`
  again.
- `refusing unsafe file name '...'`: the name contains a path separator. Download that game by
  hand.
- A bare exception name such as `ReadTimeout`: a network problem. Check the connection and proxy.

## `<url>: <what>. The site layout may have changed; ...`

Cause: a page lacks something romledger expects (game rows, a download link, a file list), so the
site has changed or is serving an error page. `fetch` stops using that source for the run and
exits 1. Fix: download by hand, and update romledger or report it.

## `<url>: not fetched, <host>/robots.txt disallows it for user agent romledger`

Cause: the site's robots.txt forbids that URL, or could not be read. `fetch` skips the source for
the run and does not count it as a failure. Fix: honor it, and download by hand.

## `warning: ambiguous: <game> matches N ConsoleRoms rows; skipped`

Cause: several ConsoleRoms rows fit the game's title. Fix: download that game by hand.

## `warning: skipping <source>: ...`

Cause: the source was blocked or changed (the message after the colon says which; see the entries
above). The rest of the games use the remaining sources.

## `Proxy password for <user>@<host>:`

Not an error: the proxy URL has a user name and no password, and `fetch` or `dats update` is
running on a terminal. Type the password; it is not shown. Without a terminal, put the password in
the URL or in `HTTPS_PROXY`.

## `finding <key>: <title>`

Cause: `canary` found drift; the exit status is 1. Run `romledger canary --json` for the detail.

Maintainers: see the key list in [CONTRIBUTING.md](https://github.com/kjiwa/romledger/blob/master/CONTRIBUTING.md#drift-checks).

## `unverified <prefix>`

Not an error: `canary` could not check the keys that start with the prefix, because a site did not
answer (see the `note:` lines) or an earlier page did not give it what it needed. Open issues for
those keys stay open. Run it again later.

## `note: <url>: ...`

Not an error: `canary` could not conclude for that site (`HTTP 403`, `HTTP 429`, `HTTP 5xx`, any
other unexpected status, `request failed (...)`, `bot challenge page`, or a robots.txt refusal) and skipped its other
checks. The exit status is not affected. Run it again later. A rate limit on GitHub's API clears
by itself; set `GITHUB_TOKEN` to raise it.

## `Run "romledger extension install", then reload the extension.`

Shown by the browser extension. Cause: the browser does not know how to start romledger, or the
host manifest names another extension. Fix: run `romledger extension install`, reload the extension,
and check `romledger extension status`. In Firefox, load the extension again after a restart.

## `The romledger host stopped: ...`

Shown by the browser extension. Cause: the program the browser started exited, for example because
`romledger extension install` recorded a Python that was since removed, or the config file moved.
Fix: run `romledger extension status`; run `romledger extension install` again if it says `stale` or
`broken`.

## `<dir> is not an inbox. Add it to library.inboxes in <config>.`

Shown by the browser extension after a download. Cause: the file landed in a folder that is not an
inbox, so it was not imported. Fix: add that folder (usually `~/Downloads/romledger`) to
`library.inboxes`.

## `waiting for another import to finish ...`

Not an error: an import (from the command line, `--watch` or the extension) holds the lock in the
data directory, and this one starts when it finishes.

## `... page layout not recognized: ...`

Shown in the extension popup. Cause: Vimm's Lair changed its markup, so the extension
found no game data or links. Fix: report it.
