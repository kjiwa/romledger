# Sources

A source is automated only if it offers an official API, or its robots.txt and terms allow
automated access, or you hold the owner's permission. Crawling a site requires the site operator's
permission; you are responsible for having it before you list a source. All other sources are
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
- Needs the site operator's permission to crawl.

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
