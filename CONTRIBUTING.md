# Contributing

## Set up and check

You need [uv](https://docs.astral.sh/uv/) and Node.js 22.22+.

```sh
uv sync
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest -q
npx --yes markdownlint-cli2@0.23.3 "**/*.md"
```

Tests marked `igir` run the real igir and are skipped by default; run them with
`uv run pytest -m igir --no-cov`.

## Extension

```sh
node --test "tests/extension/*.test.js"
npx --yes addons-linter@10.14.0 extension
sh scripts/extension-check.sh
```

`extension-check.sh` loads the unpacked extension in Chromium against a fictional library and
fixture pages, with the real native host (`romledger.native`) answering through the browser's
native messaging. With a directory argument it also writes the popup screenshots. `addons-linter` warns that Firefox ignores `background.service_worker`; that key is
for Chrome, and Firefox uses `background.scripts`. The page parsers are in `extension/content/` and
`extension/lib/romledger.js`.

## Drift checks

`romledger canary` makes about 50 requests to detect site changes before a download fails. It needs
no config file and follows the same robots.txt and spacing rules as `fetch`. The weekly
`canary` workflow runs it; run it by hand with `romledger canary` or `romledger canary --json`.

It checks that:

- Vimm's Lair `/vault/` lists every `vimm` code in the registry, and one list page has game rows.
  Game pages are never requested.
- ConsoleRoms' sitemap lists every `consoleroms` code in the registry, one listing page parses, and
  one download page still holds a link. The link itself is never requested.
- Every DAT named in `src/romledger/platforms.toml` exists in libretro-database.
- The latest igir release matches `IGIR_VERSION`.

A finding means a site, the registry, or a pin needs a change. Each has a stable key such as
`vimm:new-platform:Amiga`, `vimm:missing-platform:PS3`, `consoleroms:contract:listing`,
`dat:missing:nes`, or `igir:update:v5.8.0`. `contract` keys mean a page changed shape; a platform
index page with no platform links at all is `<site>:contract:platform-links`, while a registry code
absent from an otherwise normal index is `<site>:missing-platform:<code>`. `dat:missing` means HTTP
404. The command exits 1 when there are findings.

A note means a check could not conclude: a network error, HTTP 403, 429, or 5xx, any other
unexpected status, a bot challenge page, a robots.txt refusal, or (for GitHub's API) a redirect.
Notes are not findings and leave the exit status at 0. The rest of that site's checks are skipped
and listed as unverified: `--json` prints `{"findings": [...], "inconclusive": [...]}`, where
`inconclusive` holds the key prefixes (`vimm`, `consoleroms`, `dat`, `igir`, and
the skipped checks' keys) that were not verified; without `--json` they print as
`unverified <prefix>`. The ConsoleRoms download check is also unverified when the listing page gave
no row to use. The next run tries again.

The workflow runs `scripts/canary-issues.sh` on the JSON. It opens one issue titled
`canary: <key>` per finding, leaves an open one alone, and closes an open one with a comment once
its finding is gone, unless its key starts with an unverified prefix. A finding whose issue was
closed as completed opens a new issue; close the issue as "not planned" to silence it.

To support a platform a site lists, add its code to that platform's row in
`src/romledger/platforms.toml`, or add a new row with `dat`, `vimm`, and `consoleroms` keys. To decline
it, add the code to the `[ignore]` table in the same file.

Fix by key:

- `<site>:new-platform:<code>`: the site lists a platform the registry does not know. Add
  `<site> = "<code>"` to that platform in `src/romledger/platforms.toml`, or add the code to
  `[ignore]` there.
- `<site>:missing-platform:<code>`: the site's platform list no longer has a registry code. Correct
  the code in `platforms.toml`.
- `<site>:contract:platform-links`: the site's platform index page has no platform links. Update
  romledger or report it.
- `consoleroms:contract:listing`, `consoleroms:contract:download-link`, `vimm:contract:list`: a
  page no longer has what romledger expects, so `fetch` or the extension for that source will fail
  the same way. Update romledger or report it.
- `dat:missing:<slug>`: libretro-database has no such DAT. Correct `dat` for that platform in
  `platforms.toml`.
- `igir:update:<tag>`: a newer igir exists. Run `uv run pytest -m igir --no-cov`, then update
  `IGIR_VERSION` in `src/romledger/igir.py`.
- `igir:contract:release`: GitHub's release answer has no tag name. Report it.

## Release

Releases use [gh-cut](https://github.com/kjiwa/gh-cut): `gh cut <version>` bumps the version in
`pyproject.toml`, `extension/manifest.json` and `uv.lock` through `scripts/release-hooks.sh`, merges
the bump, tags it and creates the GitHub release. Add the version's section to `CHANGELOG.md`
first. Publishing the release runs `.github/workflows/publish.yml`.
