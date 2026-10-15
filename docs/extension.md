# Browser extension

The extension marks games on Vimm's Lair, CoolROM, ConsoleRoms, emu-land and the Internet Archive as in your library, in
your inbox, missing or not wanted, so you can browse and pick what to download. On Vimm's Lair it
can also download the missing games of a list page for you; that is off until you turn it on (see
[Download from Vimm's Lair](#download-from-vimms-lair)). Nothing else clicks or downloads.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/extension-popup-dark.png">
  <img alt="The extension popup: a progress bar and a count of wanted games had for each configured platform." src="images/extension-popup-light.png">
</picture>

## Install

The extension is not in any browser store. Download `romledger-extension-<version>.zip` from the
[latest release](https://github.com/kjiwa/romledger/releases/latest) and unzip it. A source
checkout works too: use its `extension` folder. After unzipping over an older copy, press Reload on
the extension's card in `chrome://extensions`; until then the browser keeps running the old version.

- Chrome and other Chromium browsers: open `chrome://extensions`, turn on Developer mode, choose
  Load unpacked, and select the unzipped folder.
- Firefox 142 or later: open `about:debugging#/runtime/this-firefox`, choose Load Temporary
  Add-on, and select `manifest.json` in the unzipped folder. Firefox removes a temporary add-on
  when it closes, so repeat this after each restart. Firefox support is checked with
  `addons-linter` only; it is untested in a real Firefox.

## Connect it to romledger

1. Run `romledger serve` and keep the link it prints.
2. Open the extension's options. Enter the service URL (the field starts as `http://127.0.0.1:8730`, for a service on this
   machine) and the token (the part after `?token=` in the link).
3. Choose Save and test, then allow the browser to reach that address. The page reports the
   number of configured platforms.

The URL and token stay in this browser. The extension sends the SHA-1 hashes and titles it finds
on a page only to that address.

## Download from Vimm's Lair

Optional, off by default, and Chromium-only. In the options, tick "Download from Vimm's Lair into
Downloads/romledger". The browser asks for the `downloads` permission. Untick it to give the
permission back. Firefox does not offer the event this needs, so the option is hidden there.

With it on, every download that comes from Vimm's Lair (a `*.vimm.net` host) is saved into
`Downloads/romledger` under the file name the site gave, and a list page gets a "Download N
missing" box. The button downloads each game marked Missing, one at a time, in the order of the
page, and shows the saved path of each. Keep the tab open until it says Finished. Games matched by
title (approximate) are included, so check their region and version first.

Each download starts from the Vimm's Lair page the way a click on its Download button does. Games
start at least 15 seconds apart. The queue stops at the first failed download, or when Vimm's Lair
answers that you are going too fast; wait a while before starting it again. Chrome may ask once to
allow Vimm's Lair to download multiple files.

Vimm's Lair asks for a Turnstile check before it offers a download. The extension never solves it.
When a game page comes back without a download form, the queue pauses; open any game page, pass
the check, and press Resume.

Add `~/Downloads/romledger` as an inbox (`romledger init` offers to) and `romledger serve` imports
the files by itself; see [serve](setup.md#serve).

## What it shows

| Site | Page | What you see |
| --- | --- | --- |
| Vimm's Lair | A game (`/vault/<id>`) | A box with the state of each disc or file, matched by SHA-1 and then by title. |
| Vimm's Lair | A platform list, including each letter page | A badge after every game, matched by title. |
| CoolROM | A game or a platform listing | A badge by title. |
| ConsoleRoms | A game or a platform listing | A badge by title. |
| emu-land | A game or a platform listing | A badge by title. |
| Internet Archive | An item that you set as a platform's `archive_item` | The platform's progress. |

| Badge | Meaning |
| --- | --- |
| In library | The library has the game. |
| In inbox | The game is in an inbox and `import` has not filed it. |
| Missing | The DAT lists the game, you want it, and you do not have it. |
| Not wanted | The DAT lists it, but the platform's regions, languages or `include` leave its title out. |
| Not scanned | The platform has no scan yet. Run `romledger scan`. |
| Not in any DAT | No DAT for a configured platform lists it. |

A badge that says `(approximate)` was matched by title. On Vimm's Lair lists the row's region
flags narrow the match; when several games still fit, the badge shows the best state among them.
Check the region and version before you rely on it. Platforms that are not in your config get no badges.

Vimm's Lair offers some GameCube games in extra formats (`ciso`, `nkit`, `rvz`). Only the
default ISO matches a Redump DAT, so download that one.

The toolbar popup lists every platform's progress. If it says the page layout was not recognized,
the site changed; see [troubleshooting.md](troubleshooting.md).
