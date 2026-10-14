"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const romledger = require("../../extension/lib/romledger.js");

const SOURCE = fs.readFileSync(path.join(__dirname, "../../extension/background.js"), "utf8");
const VIMM = { url: "https://dl3.vimm.net/", filename: "/home/user/Downloads/Game (USA).zip" };

function load(stored, downloads = true) {
  const added = [];
  const chrome = {
    storage: { local: { get: async () => stored } },
    runtime: { onMessage: { addListener() {} } },
    permissions: { onAdded: { addListener: (listener) => added.push(listener) } },
  };
  const listeners = [];
  if (downloads) {
    chrome.downloads = { onDeterminingFilename: { addListener: (l) => listeners.push(l) } };
  }
  vm.runInNewContext(SOURCE, { chrome, romledger, fetch() {}, URLSearchParams });
  return { listeners, added };
}

function decide(listener, item) {
  let returned;
  const suggested = new Promise((resolve) => {
    returned = listener(item, (suggestion) => resolve(suggestion));
  });
  return suggested.then((suggestion) => ({ suggestion, returned }));
}

test("a Vimm download is routed once the option is on", async () => {
  const { listeners } = load({ routeDownloads: true });
  const { suggestion, returned } = await decide(listeners[0], VIMM);
  assert.deepEqual({ ...suggestion }, {
    filename: "romledger/Game (USA).zip",
    conflictAction: "uniquify",
  });
  assert.equal(returned, true);
});

test("a Vimm download passes through when the option is off", async () => {
  const { listeners } = load({});
  const { suggestion } = await decide(listeners[0], VIMM);
  assert.equal(suggestion, undefined);
});

test("other downloads pass through synchronously", async () => {
  const { listeners } = load({ routeDownloads: true });
  const { suggestion, returned } = await decide(listeners[0], {
    url: "https://example.com/a.zip",
    filename: "/x/a.zip",
  });
  assert.equal(suggestion, undefined);
  assert.equal(returned, undefined);
});

test("the listener attaches when the permission arrives later", () => {
  const { listeners, added } = load({}, false);
  assert.equal(listeners.length, 0);
  assert.equal(added.length, 1);
});
