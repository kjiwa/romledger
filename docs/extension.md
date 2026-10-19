# Browser extension

The extension marks games for supported sources as in your library, in your inbox, missing or not
wanted, so you can browse and pick what to download. It can also download the missing games of a
list page for you; that is off until you turn it on (see
[Download from Vimm's Lair](#download-from-vimms-lair)). Nothing else clicks or downloads.

The only source that works in the browser today is Vimm's Lair; [sources.md](sources.md) says
which sources work where, and why. Every supported source gets the same features: a badge on each
game, the state of each disc on a game page, and the download queue.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/extension-popup-dark.png">
  <img alt="The extension popup: the last import, then a progress bar and a count of wanted games had for each platform that has games." src="images/extension-popup-light.png">
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

1. Run `romledger extension install`. It tells each browser it finds how to start romledger.
2. Reload the extension on `chrome://extensions` (or load it, see above).
3. Open the extension's options. The page checks the connection and reports the number of
   platforms that have games; choose Check connection to try again.

The browser starts romledger itself when the extension needs it, so nothing runs in the
background and nothing listens on the network. The extension sends the SHA-1 hashes and titles
it finds on a page only to that program, on this computer. The browser and romledger must be on
the same machine. `romledger extension status` shows which browsers are connected.

## Download from Vimm's Lair

Optional, off by default, and Chromium-only. In the options, tick "Download from Vimm's Lair into
Downloads/romledger". The browser asks for the `downloads` permission. Untick it to give the
permission back. Firefox does not offer the event this needs, so the options say so and offer
nothing there. While the option is off, a list page's box says so and has an Open options button
instead of the download button.

With it on, every download that comes from Vimm's Lair (a `*.vimm.net` host) is saved into
`Downloads/romledger` under the file name the site gave, and a list page gets a "Download N
missing" box. The button downloads each game marked Missing, one at a time, in the order of the
page, and shows the saved path of each. Keep the tab open until it says Finished. Games matched by
title (approximate) are included, so check their region and version first.

Each download starts from the Vimm's Lair page the way a click on its Download button does. Games
start at least the "Wait between downloads" set in the options apart: 15 seconds by default, and
from 15 to 600. A longer wait is gentler on the site. The queue stops at the first failed
download, and says why beside the game, or when Vimm's Lair answers that you are going too fast; wait a while before starting it again. Chrome may ask once to
allow Vimm's Lair to download multiple files.

Vimm's Lair asks for a Turnstile check before it offers a download. The extension never solves it.
When a game page comes back without a download form, the queue pauses; open any game page, pass
the check, and press Resume.

Add `~/Downloads/romledger` as an inbox (`romledger init` offers to) and the extension imports
each file as soon as its download finishes. The popup shows the outcome of the last import. Files
you copy into an inbox yourself are filed by `romledger import`, or by `romledger import --watch`
while it runs.

## What it shows

| Site | Page | What you see |
| --- | --- | --- |
| Vimm's Lair | A game (`/vault/<id>`) | A box with the state of each disc or file, matched by SHA-1 and then by title. |
| Vimm's Lair | A platform list, including each letter page | A badge after every game, matched by title. |

| Badge | Meaning |
| --- | --- |
| In library | The library has the game. |
| In inbox | The game is in an inbox and `import` has not filed it. |
| Missing | The DAT lists the game, you want it, and you do not have it. |
| Not wanted | The DAT lists it, but the platform's regions, languages or `include` leave its title out. |
| Not scanned | The platform has no scan yet. Run `romledger scan`. |
| Not in any DAT | No DAT lists it. |

A badge that says `(approximate)` was matched by title. On Vimm's Lair lists the row's region
flags narrow the match; when several games still fit, the badge shows the best state among them.
Check the region and version before you rely on it.

Vimm's Lair offers some GameCube games in extra formats (`ciso`, `nkit`, `rvz`). Only the
default ISO matches a Redump DAT, so download that one.

Each box on a page has a Close button; reload the page to bring it back.

The toolbar popup lists the progress of each platform that has games and when the last import ran.
If it says the page layout was not recognized, the site changed; see
[troubleshooting.md](troubleshooting.md).
