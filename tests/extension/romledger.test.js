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
  assert.equal(romledger.archiveItemFromPath("/details/No-Intro_NES"), "No-Intro_NES");
  assert.equal(romledger.archiveItemFromPath("/search"), null);
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
