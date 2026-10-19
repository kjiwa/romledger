"use strict";

const assert = require("node:assert/strict");
const { test } = require("node:test");

const romledger = require("../../extension/lib/romledger.js");

test("slugFor matches a site code case-insensitively", () => {
  const platforms = [
    { slug: "nes", sites: { vimm: "NES", consoleroms: null } },
    { slug: "genesis", sites: { vimm: "Genesis", consoleroms: "genesis" } },
  ];
  assert.equal(romledger.slugFor(platforms, "vimm", "GENESIS"), "genesis");
  assert.equal(romledger.slugFor(platforms, "vimm", "nes"), "nes");
  assert.equal(romledger.slugFor(platforms, "vimm", "SNES"), null);
  assert.equal(romledger.slugFor(platforms, "vimm", ""), null);
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

test("progress words a scanned and an unscanned platform", () => {
  assert.equal(romledger.progress({ percent: null }), "Not scanned");
  assert.equal(
    romledger.progress({ have: 96, wanted: 180, percent: 53 }),
    "96 of 180 wanted games (53%)",
  );
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

test("a registered site is found by host and recognises its own downloads", () => {
  const site = {
    id: "demo",
    hosts: ["demo.example"],
    isDownload: (item) => item.url === "https://dl.demo.example/x",
  };
  romledger.register(site);
  assert.equal(romledger.siteFor("demo.example"), site);
  assert.equal(romledger.siteFor("other.example"), null);
  assert.equal(romledger.isSiteDownload({ url: "https://dl.demo.example/x" }), true);
  assert.equal(romledger.isSiteDownload({ url: "https://elsewhere.example/x" }), false);
  delete romledger.sites.demo;
  assert.equal(romledger.siteFor("demo.example"), null);
});

test("gapSeconds defaults, clamps and ignores what is not a number", () => {
  assert.equal(romledger.gapSeconds(undefined), 15);
  assert.equal(romledger.gapSeconds(null), 15);
  assert.equal(romledger.gapSeconds(""), 15);
  assert.equal(romledger.gapSeconds("soon"), 15);
  assert.equal(romledger.gapSeconds(Infinity), 15);
  assert.equal(romledger.gapSeconds(30), 30);
  assert.equal(romledger.gapSeconds("45"), 45);
  assert.equal(romledger.gapSeconds(1), 15);
  assert.equal(romledger.gapSeconds(100000), 600);
});

test("ago words how long it has been", () => {
  const now = 1_000_000_000;
  assert.equal(romledger.ago(now - 5_000, now), "just now");
  assert.equal(romledger.ago(now - 60_000, now), "1 minute ago");
  assert.equal(romledger.ago(now - 3 * 3_600_000, now), "3 hours ago");
  assert.equal(romledger.ago(now - 2 * 86_400_000, now), "2 days ago");
  assert.equal(romledger.ago(now + 5_000, now), "just now");
});

test("progress groups thousands", () => {
  assert.equal(
    romledger.progress({ have: 1234, wanted: 2000, percent: 61 }),
    "1,234 of 2,000 wanted games (61%)",
  );
});
