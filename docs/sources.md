# Sources

A source is a site romledger can get games from. What it can do with one follows from how the site
may be used, so nothing is configured per platform. `romledger platforms` shows which sources carry
each platform.

| Source | Command line (`fetch`) | Browser extension | Matched by |
| --- | --- | --- | --- |
| Vimm's Lair | no | yes | SHA-1, then title |
| ConsoleRoms | yes | no | title |

A site is fetched from the command line only if it offers an official API, or its robots.txt and
terms allow automated access, or you hold the site owner's permission. You are responsible for
having it before you use `fetch` on a site. Every other site is browser-only: a person downloads in
the browser, into an inbox, and the next import files it (see
[Where files go](setup.md#where-files-go)). A site is matched by hash only where it publishes
hashes; otherwise by title, which can pick another region's dump.

romledger identifies itself as `romledger/<version> (+https://github.com/kjiwa/romledger)`, never
as a browser. If a site refuses it, `fetch` reports the error and stops using that site.

Downloads from every source land in an inbox, and `import` verifies them against the DAT by
content. The DAT check is the integrity gate; a wrong or corrupt file is filed under
`<inbox>/unmatched/`, and a valid dump of another release under `<inbox>/unwanted/`. `fetch` does
not download a file again while the earlier copy sits in either folder.

## ConsoleRoms

Source name `consoleroms`, hosts `www.consoleroms.com` and `downloads.consoleroms.com`. Carries
about thirty of the registry's platforms, Nintendo systems included. `fetch` asks it only about
platforms it carries.

- Games are matched by title with tags and punctuation ignored. Only a unique match is used; an
  ambiguous title is skipped with a warning, and you download it by hand.
- Listings show no region, so a download may be another region's dump or one the DAT does not
  list; either way `import` sets it aside and `fetch` skips that title next time.
- Downloads are zip or 7z files. ConsoleRoms publishes no hashes.
- It follows `robots.txt`, which allows crawling, and honours any crawl delay it sets. It keeps at
  least 1 second between requests.
- Crawl it only if the site's terms and permission allow; see the top of this page.

## Vimm's Lair

Browser only. Game pages sit behind a Cloudflare Turnstile challenge, which only a person in a
browser passes, so romledger never fetches from them. The automation that is possible is on your
side of the challenge:

- `romledger missing PLATFORM --links` prints a search link per game.
- The [browser extension](extension.md) marks what you have and can save Vimm's Lair downloads
  into an inbox, where the extension imports them.

Partial browser downloads are skipped until finished.

## Not supported yet

None of these has been evaluated against the rule above, so nothing is claimed about their terms.
Check a site's robots.txt and terms before adding it.

- Minerva Archive (unverified)
- CDRomance (unverified)
- EdgeEmu (unverified)
- romulation.org (unevaluated)
