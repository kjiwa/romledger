"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");

const romledger = require("../../extension/lib/romledger.js");

function fixture(name) {
  return fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8");
}

test("parseAllMedia reads one entry per disc", () => {
  const discs = romledger.parseAllMedia(fixture("vimm-baten.html"));
  assert.deepEqual(
    discs.map((disc) => [disc.name, disc.sha1]),
    [
      ["Baten Kaitos Origins (USA, Canada) (Disc 1)", "b5e6aafae4aa171caa558875ca7d66b465a78f7f"],
      ["Baten Kaitos Origins (USA, Canada) (Disc 2)", "706774280ed6dba841a9ed600066f8773c80a8c0"],
    ],
  );
});

test("parseAllMedia reads a single cartridge entry", () => {
  const [disc] = romledger.parseAllMedia(fixture("vimm-pokemon.html"));
  assert.equal(disc.name, "Pokemon X (USA) (En,Ja,Fr,De,Es,It,Ko)");
  assert.equal(disc.sha1, "20b7278f10a32ab440b4dff1d382a1401590aceb");
});

test("parseAllMedia returns null for a changed layout", () => {
  assert.equal(romledger.parseAllMedia("var other = 1;"), null);
  assert.equal(romledger.parseAllMedia("allMedia=[not json];"), null);
  assert.equal(romledger.parseAllMedia('allMedia=[{"GoodTitle":"%%%","GoodSha1":"x"}];'), null);
  assert.equal(romledger.parseAllMedia('allMedia=[{"GoodTitle":"","GoodSha1":"x"}];'), null);
});

test("site codes come from titles and paths", () => {
  assert.equal(romledger.vimmSystemFromTitle("The Vault: Pokemon X (3DS)"), "3DS");
  assert.equal(romledger.vimmSystemFromTitle("The Vault: Something"), null);
  assert.equal(romledger.coolromSystemFromPath("/roms/genesis/6013/Sagaia.php"), "genesis");
  assert.equal(romledger.coolromSystemFromPath("/other"), null);
  assert.equal(
    romledger.coolromNameFromPath("/roms/genesis/47761/Saint_Sword_(Japan).php"),
    "Saint Sword (Japan)",
  );
  assert.equal(romledger.coolromNameFromPath("/roms/genesis/1/100%_Fun.php"), "100% Fun");
  assert.equal(romledger.consoleromsSystemFromPath("/roms/atari-7800"), "atari-7800");
  assert.equal(romledger.consoleromsSystemFromPath("/roms/atari-7800/page/2"), "atari-7800");
  assert.equal(romledger.consoleromsSystemFromPath("/tags/action"), null);
  assert.equal(romledger.consoleromsGameSlug("/roms/atari-7800/galaga"), "galaga");
  assert.equal(romledger.consoleromsGameSlug("/roms/atari-7800"), null);
  assert.equal(romledger.consoleromsGameSlug("/roms/atari-7800/page"), null);
  assert.equal(romledger.consoleromsGameSlug("/roms/atari-7800/page/2"), null);
  assert.equal(romledger.consoleromsGameSlug("/roms/atari-7800/galaga/download"), null);
  assert.equal(romledger.emulandSystemFromPath("/en/consoles/dendy/roms/x"), "consoles/dendy");
  assert.equal(romledger.emulandSystemFromPath("/portable/gb"), "portable/gb");
  assert.equal(romledger.emulandSystemFromPath("/en/news/today"), null);
  assert.equal(romledger.emulandSystemFromPath("/en"), null);
  assert.equal(romledger.archiveItemFromPath("/details/No-Intro_NES"), "No-Intro_NES");
  assert.equal(romledger.archiveItemFromPath("/search"), null);
});

test("emulandGameSlug accepts game pages and skips index pages", () => {
  assert.equal(romledger.emulandGameSlug("/en/consoles/dendy/roms/xevious"), "xevious");
  assert.equal(romledger.emulandGameSlug("/computers/dos/games/doom"), "doom");
  assert.equal(romledger.emulandGameSlug("/en/consoles/psx/iso/gran-turismo"), "gran-turismo");
  for (const index of ["x", "0-9", "a-z", "best", "homebrew", "misc", "top"]) {
    assert.equal(romledger.emulandGameSlug(`/en/consoles/dendy/roms/${index}`), null, index);
  }
  assert.equal(romledger.emulandGameSlug("/en/consoles/dendy/roms"), null);
  assert.equal(romledger.emulandGameSlug("/en/consoles/dendy/news/xevious"), null);
  assert.equal(romledger.emulandGameSlug("/en/news/dendy/roms/xevious"), null);
});

test("slugFor matches a site code case-insensitively", () => {
  const platforms = [
    { slug: "nes", sites: { vimm: "NES", coolrom: null } },
    { slug: "genesis", sites: { vimm: "Genesis", coolrom: "genesis" } },
  ];
  assert.equal(romledger.slugFor(platforms, "coolrom", "GENESIS"), "genesis");
  assert.equal(romledger.slugFor(platforms, "vimm", "nes"), "nes");
  assert.equal(romledger.slugFor(platforms, "vimm", "SNES"), null);
  assert.equal(romledger.slugFor(platforms, "coolrom", ""), null);
});

test("describe labels every state and marks approximate matches", () => {
  assert.deepEqual(romledger.describe({ state: "have", exact: true }), {
    text: "In library",
    kind: "have",
    approximate: false,
  });
  assert.equal(romledger.describe({ state: "missing", exact: false }).text, "Missing (approximate)");
  assert.equal(romledger.describe({ state: "unknown", exact: false }).approximate, false);
  assert.equal(romledger.describe({ state: "nonsense", exact: true }).kind, "unknown");
});

test("best picks the most useful state and marks a choice approximate", () => {
  const match = (state, game) => ({ platform: "nes", game, state, exact: false });
  const picked = romledger.best([match("missing", "A"), match("have", "B"), match("unwanted", "C")]);
  assert.equal(picked.state, "have");
  assert.equal(picked.game, "B");
  assert.equal(picked.exact, false);
  const exact = { platform: "nes", game: "A", state: "missing", exact: true };
  assert.deepEqual(romledger.best([exact]), exact);
  assert.equal(romledger.best([]).state, "unknown");
  const fallback = { state: "missing", exact: true };
  assert.equal(romledger.best([], fallback), fallback);
  assert.equal(romledger.best([match("unknown", "A"), match("unwanted", "B")]).state, "unwanted");
  assert.equal(romledger.best([match("inbox", "A"), match("missing", "B")]).state, "inbox");
});

test("regionsOf reads the flag titles of a Vimm list row", () => {
  const rows = fixture("vimm-list-10-yard-fight.html")
    .split("</tr>")
    .filter((html) => html.includes("<tr>"))
    .map((html) => ({
      querySelectorAll: (selector) => {
        assert.equal(selector, "img.flag");
        return [...html.matchAll(/<img[^>]*class="flag"[^>]*title="([^"]+)"/g)].map((found) => ({
          title: found[1],
        }));
      },
    }));
  assert.deepEqual(rows.map(romledger.regionsOf), [["USA", "Europe"], ["Japan"], ["USA"]]);
});

test("regionsOf tolerates a link outside a table row", () => {
  assert.deepEqual(romledger.regionsOf(null), []);
});

test("progress words a scanned and an unscanned platform", () => {
  assert.equal(romledger.progress({ percent: null }), "Not scanned");
  assert.equal(
    romledger.progress({ have: 96, wanted: 180, percent: 53 }),
    "96 of 180 wanted games (53%)",
  );
});

test("isVimmDownload matches only Vimm download hosts", () => {
  const yes = (item) => assert.equal(romledger.isVimmDownload(item), true);
  const no = (item) => assert.equal(romledger.isVimmDownload(item), false);
  yes({ url: "https://dl3.vimm.net/", finalUrl: "" });
  yes({ url: "https://example.com/redirect", finalUrl: "https://DL2.vimm.net/x" });
  yes({ url: "https://dl3.vimm.net/", finalUrl: "https://cdn.example.com/x" });
  no({ url: "https://vimm.net/vault/77", finalUrl: "https://vimm.net/vault/77" });
  no({ url: "https://evil-vimm.net/", finalUrl: "https://dl3.vimm.net.evil.com/" });
  no({ url: "https://example.com/vimm.net", finalUrl: "" });
  no({ url: "not a url" });
  no({});
});

test("downloadTarget keeps the file name and drops anything that could escape the folder", () => {
  const target = (filename) => romledger.downloadTarget({ filename });
  assert.equal(target("/home/user/Downloads/Game (USA).zip"), "romledger/Game (USA).zip");
  assert.equal(target("C:\\Users\\me\\Downloads\\Game.zip"), "romledger/Game.zip");
  assert.equal(target("../../etc/passwd"), "romledger/passwd");
  assert.equal(target("..hidden..zip"), "romledger/hidden..zip");
  assert.equal(target("Game v1..2.zip"), "romledger/Game v1..2.zip");
  assert.equal(target("."), null);
  assert.equal(target(".bashrc"), "romledger/bashrc");
  assert.equal(target("a\u0000b.zip"), "romledger/ab.zip");
  assert.equal(target(""), null);
  assert.equal(target(".."), null);
  assert.equal(target("dir/"), null);
  assert.equal(romledger.downloadTarget({}), null);
});

test("vimmListSystem reads the system from query and section list pages", () => {
  const system = (url) => romledger.vimmListSystem(url);
  assert.equal(system("https://vimm.net/vault/?p=list&system=GB&q="), "GB");
  assert.equal(system("https://vimm.net/vault/NES/A"), "NES");
  assert.equal(system("https://vimm.net/vault/NES/number"), "NES");
  assert.equal(system("https://vimm.net/vault/77"), null);
  assert.equal(system("https://vimm.net/vault/"), null);
});

function formDocument(action, inputs) {
  const attributes = (input) => ({ getAttribute: (name) => input[name], disabled: Boolean(input.disabled) });
  const form = {
    getAttribute: () => action,
    querySelectorAll: () => inputs.map(attributes),
  };
  return { querySelector: (selector) => (selector === "#dl-form" ? form : null) };
}

const VIMM_INPUTS = [
  { name: "mediaId", value: "9" },
  { name: "alt", value: "0", disabled: true },
  { name: "token", value: "abc" },
];

test("vimmDownloadUrl turns the Vimm form into a GET URL and leaves disabled inputs out", () => {
  const url = (action, inputs = VIMM_INPUTS) =>
    romledger.vimmDownloadUrl(formDocument(action, inputs), "https://vimm.net/vault/77");
  assert.equal(url("//dl3.vimm.net/"), "https://dl3.vimm.net/?mediaId=9&token=abc");
  assert.equal(url("http://dl3.vimm.net/"), "https://dl3.vimm.net/?mediaId=9&token=abc");
  assert.equal(url("//dl3.vimm.net/", VIMM_INPUTS.map((input) => ({ ...input, disabled: false }))),
    "https://dl3.vimm.net/?mediaId=9&alt=0&token=abc");
});

test("vimmDownloadUrl refuses other hosts, missing fields and a missing form", () => {
  const url = (action, inputs = VIMM_INPUTS) =>
    romledger.vimmDownloadUrl(formDocument(action, inputs), "https://vimm.net/vault/77");
  assert.equal(url("//evil.example/"), null);
  assert.equal(url("//vimm.net.evil.example/"), null);
  assert.equal(url(""), null);
  assert.equal(url("//dl3.vimm.net/", VIMM_INPUTS.slice(0, 2)), null);
  assert.equal(romledger.vimmDownloadUrl({ querySelector: () => null }, "https://vimm.net/vault/77"), null);
});

test("queueable keeps every missing game and counts the approximate ones", () => {
  const entry = (title, match) => ({ title, match });
  const { ready, approximate } = romledger.queueable([
    entry("A", { state: "missing", exact: true }),
    entry("B", { state: "missing", exact: false }),
    entry("C", { state: "have", exact: true }),
    entry("D", { state: "unknown" }),
    entry("E", { state: "missing" }),
  ]);
  assert.deepEqual(ready.map((item) => item.title), ["A", "B", "E"]);
  assert.equal(approximate, 1);
});
