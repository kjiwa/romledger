"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");

const vimm = require("../../extension/sites/vimm.js");

function fixture(name) {
  return fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8");
}

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

test("parseAllMedia reads one entry per disc", () => {
  const discs = vimm.parseAllMedia(fixture("vimm-baten.html"));
  assert.deepEqual(
    discs.map((disc) => [disc.name, disc.sha1]),
    [
      ["Baten Kaitos Origins (USA, Canada) (Disc 1)", "b5e6aafae4aa171caa558875ca7d66b465a78f7f"],
      ["Baten Kaitos Origins (USA, Canada) (Disc 2)", "706774280ed6dba841a9ed600066f8773c80a8c0"],
    ],
  );
});

test("parseAllMedia reads a single cartridge entry", () => {
  const [disc] = vimm.parseAllMedia(fixture("vimm-pokemon.html"));
  assert.equal(disc.name, "Pokemon X (USA) (En,Ja,Fr,De,Es,It,Ko)");
  assert.equal(disc.sha1, "20b7278f10a32ab440b4dff1d382a1401590aceb");
});

test("parseAllMedia returns null for a changed layout", () => {
  assert.equal(vimm.parseAllMedia("var other = 1;"), null);
  assert.equal(vimm.parseAllMedia("allMedia=[not json];"), null);
  assert.equal(vimm.parseAllMedia('allMedia=[{"GoodTitle":"%%%","GoodSha1":"x"}];'), null);
  assert.equal(vimm.parseAllMedia('allMedia=[{"GoodTitle":"","GoodSha1":"x"}];'), null);
});

test("the Vimm system comes from the page title", () => {
  assert.equal(vimm.systemFromTitle("The Vault: Pokemon X (3DS)"), "3DS");
  assert.equal(vimm.systemFromTitle("The Vault: Something"), null);
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
  assert.deepEqual(rows.map(vimm.regionsOf), [["USA", "Europe"], ["Japan"], ["USA"]]);
});

test("regionsOf tolerates a link outside a table row", () => {
  assert.deepEqual(vimm.regionsOf(null), []);
});

test("isDownload matches only Vimm download hosts", () => {
  const yes = (item) => assert.equal(vimm.isDownload(item), true);
  const no = (item) => assert.equal(vimm.isDownload(item), false);
  yes({ url: "https://dl3.vimm.net/", finalUrl: "" });
  yes({ url: "https://example.com/redirect", finalUrl: "https://DL2.vimm.net/x" });
  yes({ url: "https://dl3.vimm.net/", finalUrl: "https://cdn.example.com/x" });
  no({ url: "https://vimm.net/vault/77", finalUrl: "https://vimm.net/vault/77" });
  no({ url: "https://evil-vimm.net/", finalUrl: "https://dl3.vimm.net.evil.com/" });
  no({ url: "https://example.com/vimm.net", finalUrl: "" });
  no({ url: "not a url" });
  no({});
});

test("listSystem reads the system from query and section list pages", () => {
  const system = (url) => vimm.listSystem(url);
  assert.equal(system("https://vimm.net/vault/?p=list&system=GB&q="), "GB");
  assert.equal(system("https://vimm.net/vault/NES/A"), "NES");
  assert.equal(system("https://vimm.net/vault/NES/number"), "NES");
  assert.equal(system("https://vimm.net/vault/77"), null);
  assert.equal(system("https://vimm.net/vault/"), null);
  assert.equal(system("https://vimm.net/vault/search/foo"), null);
  assert.equal(system("https://vimm.net/vault/N%E0%A4%A/A"), "N%E0%A4%A");
});

test("downloadUrl turns the Vimm form into a GET URL and leaves disabled inputs out", () => {
  const url = (action, inputs = VIMM_INPUTS) =>
    vimm.downloadUrl(formDocument(action, inputs), "https://vimm.net/vault/77");
  assert.equal(url("//dl3.vimm.net/"), "https://dl3.vimm.net/?mediaId=9&token=abc");
  assert.equal(url("http://dl3.vimm.net/"), "https://dl3.vimm.net/?mediaId=9&token=abc");
  assert.equal(url("//dl3.vimm.net/", VIMM_INPUTS.map((input) => ({ ...input, disabled: false }))),
    "https://dl3.vimm.net/?mediaId=9&alt=0&token=abc");
});

test("downloadUrl refuses other hosts, missing fields and a missing form", () => {
  const url = (action, inputs = VIMM_INPUTS) =>
    vimm.downloadUrl(formDocument(action, inputs), "https://vimm.net/vault/77");
  assert.equal(url("//evil.example/"), null);
  assert.equal(url("//vimm.net.evil.example/"), null);
  assert.equal(url(""), null);
  assert.equal(url("//dl3.vimm.net/", VIMM_INPUTS.slice(0, 2)), null);
  assert.equal(vimm.downloadUrl({ querySelector: () => null }, "https://vimm.net/vault/77"), null);
});

function page(scripts, links = []) {
  return {
    title: "The Vault: Pokemon X (3DS)",
    scripts: scripts.map((textContent) => ({ textContent })),
    querySelectorAll: (selector) => {
      assert.equal(selector, "td a[href]");
      return links;
    },
  };
}

const MEDIA = fixture("vimm-pokemon.html");

test("read describes a game page by its discs and system", () => {
  const view = vimm.read({ pathname: "/vault/77", href: "https://vimm.net/vault/77" }, page([MEDIA]));
  assert.equal(view.kind, "game");
  assert.equal(view.system, "3DS");
  assert.equal(view.discs[0].sha1, "20b7278f10a32ab440b4dff1d382a1401590aceb");
});

test("read reports a game page whose data is gone as unrecognized", () => {
  const view = vimm.read({ pathname: "/vault/77", href: "https://vimm.net/vault/77" }, page(["x"]));
  assert.equal(view.kind, "unrecognized");
  assert.match(view.detail, /allMedia data is missing/);
  assert.equal(vimm.read({ pathname: "/vault/77/", href: "x" }, page([])).kind, "unrecognized");
});

function link(href, text, flags = []) {
  const row = {
    querySelectorAll: () => flags.map((title) => ({ title })),
  };
  return { href, textContent: ` ${text} `, closest: () => row };
}

test("read describes a list page by its rows, titles, addresses and regions", () => {
  const links = [
    link("https://vimm.net/vault/31", "Alpha Quest", ["USA", "Europe"]),
    link("https://vimm.net/vault/?p=list&system=GB", "not a game"),
    link("https://vimm.net/vault/32", "Beta Quest"),
  ];
  const location = { pathname: "/vault/GB/A", href: "https://vimm.net/vault/GB/A" };
  const view = vimm.read(location, page([], links));
  assert.equal(view.kind, "list");
  assert.equal(view.system, "GB");
  assert.deepEqual(
    view.rows.map((row) => [row.title, row.url, row.regions]),
    [
      ["Alpha Quest", "https://vimm.net/vault/31", ["USA", "Europe"]],
      ["Beta Quest", "https://vimm.net/vault/32", []],
    ],
  );
  assert.equal(view.rows[0].link, links[0]);
});

test("read reports a list page without game links as unrecognized", () => {
  const location = { pathname: "/vault/GB/A", href: "https://vimm.net/vault/GB/A" };
  const view = vimm.read(location, page([], []));
  assert.equal(view.kind, "unrecognized");
  assert.match(view.detail, /no game links found/);
});

test("read ignores pages that are neither a game nor a list", () => {
  const location = { pathname: "/vault/", href: "https://vimm.net/vault/" };
  assert.equal(vimm.read(location, page([])), null);
});

test("the adapter names itself, its host and its wording", () => {
  assert.equal(vimm.id, "vimm");
  assert.deepEqual(vimm.hosts, ["vimm.net"]);
  assert.match(vimm.messages.slowDown, /slow down/);
  assert.match(vimm.messages.paused, /Resume/);
});
