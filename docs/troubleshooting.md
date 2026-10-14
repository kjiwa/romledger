# Troubleshooting

Errors print as `romledger: error: <message>` and exit with status 2.

## `config file not found`

Cause: no file at the path. Fix: pass `--config`, set `ROMLEDGER_CONFIG`, or create the
file from the example in the message.

## `not a directory. Is the drive or share mounted?`

Cause: `library.roms` or an inbox does not exist, usually because the drive or share is not mounted.
Fix: mount it, or correct the path in the config file.

## `unknown platform 'X'. Use one of: ...; or set dat.`

Symptom: `[platforms.X]` has no `dat` and X is not a known platform slug. Cause: typo or an
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
then run `romledger dats update` again.

## `no DAT for X (...). run: romledger dats update`

Cause: `scan` or `import` ran before the DAT was downloaded. Fix: run `romledger dats update`.

## `X has not been scanned. run: romledger scan`

Cause: `missing X` ran before the first scan. Fix: run `romledger scan X`.

## `<path>: token is shorter than 16 characters. ...`

Cause: `serve.token` in the data directory, or `ROMLEDGER_TOKEN`, is too short to be safe. Fix:
delete the file to generate a new token, or set a longer `ROMLEDGER_TOKEN`.

## `--port: 'X' is not a port between 1 and 65535`

Cause: `serve --port` got something else. Fix: pass a number in that range.

## `Missing or invalid access token` (HTTP 401)

Cause: the browser has no session or the token changed. Fix: run `romledger serve` and open the
link it prints. Scripts send `Authorization: Bearer <token>`.

## `Cross-origin requests are not allowed.` (HTTP 403)

Cause: a POST came from a page on another origin, such as a different host name or port than the
one the dashboard was opened on. Fix: open the dashboard at the address you started it on.

## `a scan is already running. Wait for it to finish.` (HTTP 409)

Cause: a scan or import was started while another runs. Fix: wait; Activity shows progress.

## `a scan is running; upload again when it finishes` (HTTP 409)

Cause: uploads are refused while a scan or import runs, so the job never sees a half-written
file. Fix: upload again when Activity shows the job finished.

## `names ending in .part are reserved for unfinished uploads`

Cause: an uploaded file name ends in `.part`. Fix: rename the file before uploading.

## `send the files as multipart/form-data`, `the upload ended early`, `the upload is malformed`

Cause: the upload was not a form, or the connection dropped mid-file. Nothing from the unfinished
file is kept. Fix: upload again, with `-F files=@<file>` from `curl`.

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

Cause: `regions` or `languages` is `[]`, which would filter out every game. Fix: list at least
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

## `<platform> has no sources configured; set platforms.<platform>.sources`

Cause: `fetch` ran for a platform with no `sources`. Fix: add `sources = ["coolrom"]` and/or
`["internet-archive"]` to `[platforms.<platform>]`; see [sources.md](sources.md).

## `<platform> does not list source 'X'. Configured sources: ...`

Cause: `--source X` names a source the platform does not use. Fix: use one of the listed names, or
add X to `platforms.<platform>.sources`.

## `platforms.X.sources has unknown source 'Y'`

Cause: typo or an unsupported source. Fix: use `coolrom` or `internet-archive`.

## `missing platforms.X.archive_item`

Cause: `internet-archive` is listed but no item is named. Fix: set `archive_item` to the Internet
Archive item that holds the platform's `<game name>.zip` files.

## `platforms.X.sources lists coolrom but CoolROM has no system for 'X'`

Cause: CoolROM does not carry the platform (no Nintendo systems), or a custom platform has no
CoolROM code. Fix: remove `coolrom` from the list.

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

## `warning: ambiguous: <game> matches N CoolROM rows; skipped`

Cause: several CoolROM rows fit the game and none is the DAT game's region. Fix: download that
game by hand.

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

## `Open the romledger options and enter the service URL and token.`

Shown by the browser extension. Cause: the options are empty. Fix: follow
[extension.md](extension.md#connect-it-to-romledger).

## `Cannot reach <url>. Is romledger serve running?`

Shown by the browser extension. Cause: nothing answers at the service URL, or the browser has no
permission for that address. Fix: start `romledger serve`, correct the URL in the options, and
choose Save and test to grant access.

## `The service rejected the token. Check it in the options.`

Shown by the browser extension. Cause: the token differs from `<data>/serve.token` or
`$ROMLEDGER_TOKEN`. Fix: copy the part after `?token=` in the link `romledger serve` prints.

## `The service answered HTTP N.`

Shown by the browser extension. Fix: read the server's output and see the entry for that status
above.

## `... page layout not recognized: ...`

Shown in the extension popup. Cause: Vimm's Lair or CoolROM changed its markup, so the extension
found no game data or links. Fix: report it.
