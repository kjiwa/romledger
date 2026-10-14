# Sources

A source is automated only if it offers an official API, or its robots.txt and terms allow
automated access, or you hold the site owner's permission. You are responsible for having it before you list a
source. All other sources are
manual: download in your browser into an inbox, then run `romledger import`.

romledger identifies itself as `romledger/<version> (+https://github.com/kjiwa/romledger)`, never
as a browser. If a site refuses it, `fetch` reports the error and stops using that site.

Downloads from every source land in the first inbox, and `import` verifies them against the DAT by
content. The DAT check is the integrity gate; a wrong or corrupt file is filed under
`<inbox>/unmatched/`.

## CoolROM

Source name `coolrom`, host `coolrom.com`. Carries about two dozen platforms and no Nintendo
systems; listing `coolrom` for a platform it does not carry is an error.

- Games are matched by title with tags and punctuation ignored. When several rows share a title,
  the one whose region equals the DAT game's first region wins (World counts as USA). Otherwise a
  unique row is used; an ambiguous title is skipped with a warning, and you download it by hand.
- It follows `robots.txt`, which asks for a 10 second crawl delay, and keeps at least that gap
  between requests. Large platforms take a while by design.
- CoolROM publishes no hashes. A download link expires about 10 minutes after the page that
  holds it, so romledger asks for the link immediately before each download.

## Internet Archive

Source name `internet-archive`, host `archive.org`, through its public metadata and download
endpoints. Set `platforms.<slug>.archive_item` to an item holding No-Intro style files named
`<DAT game name>.zip`; a game is found only by that exact name.

- The item's file list is read once per run. It carries a checksum per file; a download whose md5
  differs is deleted.
- Keeps at least 1 second between requests.
- Whether an item may be used is the uploader's and the Archive's decision; check the item's page.

## Vimm's Lair

Manual. Vimm's game pages sit behind a bot challenge, so romledger never fetches from them.
`romledger missing PLATFORM --links` prints a search link per game. Download in your browser into
an inbox, then run `romledger import`. Partial browser downloads are skipped until finished.
For GameCube, pick the default ISO; the other formats do not match the Redump DAT.

## Drift checks

`romledger canary` makes about 50 requests to detect site changes before a download fails. It needs
no config file and follows the same robots.txt and spacing rules as `fetch`. The weekly
`canary` workflow runs it; run it by hand with `romledger canary` or `romledger canary --json`.

It checks that:

- CoolROM's `/roms/` lists every `coolrom` code in the registry, one section page parses, and one
  `dlpop.php` page still holds a signed link. The link itself is never requested.
- Vimm's Lair `/vault/` lists every `vimm` code in the registry, and one list page has game rows.
  Game pages are never requested.
- The Internet Archive's metadata for `No-Intro_NES` lists files with checksums.
- Every DAT named in `src/romledger/platforms.toml` exists in libretro-database.
- The latest igir release matches `IGIR_VERSION`.

A finding means a site, the registry, or a pin needs a change. Each has a stable key such as
`vimm:new-platform:Amiga`, `vimm:missing-platform:PS3`, `coolrom:contract:section`,
`dat:missing:nes`, or `igir:update:v5.8.0`. `contract` keys mean a page changed shape; a platform
index page with no platform links at all is `<site>:contract:platform-links`, while a registry code
absent from an otherwise normal index is `<site>:missing-platform:<code>`. `dat:missing` means HTTP
404. The command exits 1 when there are findings.

A note means a check could not conclude: a network error, HTTP 403, 429, or 5xx, any other
unexpected status, a bot challenge page, a robots.txt refusal, or (for GitHub's API) a redirect.
Notes are not findings and leave the exit status at 0. The rest of that site's checks are skipped
and listed as unverified: `--json` prints `{"findings": [...], "inconclusive": [...]}`, where
`inconclusive` holds the key prefixes (`coolrom`, `vimm`, `internet-archive`, `dat`, `igir`, and
the skipped checks' keys) that were not verified; without `--json` they print as
`unverified <prefix>`. The CoolROM download check is also unverified when the section page gave no
row to use. The next run tries again.

The workflow runs `scripts/canary-issues.sh` on the JSON. It opens one issue titled
`canary: <key>` per finding, leaves an open one alone, and closes an open one with a comment once
its finding is gone, unless its key starts with an unverified prefix. A finding whose issue was
closed as completed opens a new issue; close the issue as "not planned" to silence it.

To support a platform a site lists, add its code to that platform's row in
`src/romledger/platforms.toml`, or add a new row with `dat`, `vimm`, and `coolrom` keys. To decline
it, add the code to the `[ignore]` table in the same file.
