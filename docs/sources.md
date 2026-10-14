# Sources

A source is automated only if it offers an official API, or its robots.txt and terms allow
automated access, or you hold the site owner's permission. You are responsible for having it
before you list a source. All other sources are manual: download in your browser into an inbox;
the next import files it (see [Where files go](setup.md#where-files-go)).

romledger identifies itself as `romledger/<version> (+https://github.com/kjiwa/romledger)`, never
as a browser. If a site refuses it, `fetch` reports the error and stops using that site.

Downloads from every source land in the first inbox, and `import` verifies them against the DAT by
content. The DAT check is the integrity gate; a wrong or corrupt file is filed under
`<inbox>/unmatched/`, and a valid dump of another release under `<inbox>/unwanted/`. `fetch` does
not download a file again while the earlier copy sits in either folder.

## CoolROM

Source name `coolrom`, host `coolrom.com`. Carries about two dozen platforms and no Nintendo
systems; listing `coolrom` for a platform it does not carry is an error.

- Games are matched by title with tags and punctuation ignored. When several rows share a title,
  the one whose region equals the DAT game's first region wins (World counts as USA). Otherwise a
  unique row is used; an ambiguous title is skipped with a warning, and you download it by hand.
- It follows `robots.txt`, which asks for a 10 second crawl delay, and keeps at least that gap
  between requests. Large platforms take a while by design.
- CoolROM lists one file per title, so it may be another region's dump or one the DAT does not
  list; either way `import` sets it aside and `fetch` skips that title next time.
- CoolROM publishes no hashes. A download link expires about 10 minutes after the page that
  holds it, so romledger asks for the link immediately before each download.
- Crawl it only with the site's permission; see the top of this page.

## Internet Archive

Source name `internet-archive`, host `archive.org`, through its public metadata and download
endpoints. Set `platforms.<slug>.archive_item` to an item holding No-Intro style files named
`<DAT game name>.zip`; a game is found only by that exact name.

- The item's file list is read once per run. It carries a checksum per file; a download whose md5
  differs is deleted.
- Keeps at least 1 second between requests.
- Whether an item may be used is the uploader's and the Archive's decision; check the item's page.

## Vimm's Lair

Manual. Game pages sit behind a Cloudflare Turnstile challenge, which only a person in a browser
passes, so romledger never fetches from them. The automation that is possible is on your side of
the challenge:

- `romledger missing PLATFORM --links` prints a search link per game.
- The [browser extension](extension.md) marks what you have and can save Vimm's Lair downloads
  into an inbox, where `serve` imports them.

Partial browser downloads are skipped until finished. For GameCube, pick the default ISO; the
other formats do not match the Redump DAT.

## Not supported yet

None of these has been evaluated against the rule above, so nothing is claimed about their terms.
Check a site's robots.txt and terms before adding it.

- Minerva Archive (unverified)
- CDRomance (unverified)
- EdgeEmu (unverified)
- emu-land.net (unevaluated)
- consoleroms.com (unevaluated)
- romulation.org (unevaluated)
