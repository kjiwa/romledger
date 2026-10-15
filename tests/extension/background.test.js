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

function loadMessages(stored, downloads) {
  const handlers = [];
  const chrome = {
    storage: { local: { get: async () => stored } },
    runtime: { onMessage: { addListener: (handler) => handlers.push(handler) } },
    permissions: { onAdded: { addListener() {} } },
    downloads,
  };
  vm.runInNewContext(SOURCE, { chrome, romledger, fetch() {}, URLSearchParams });
  return (message) =>
    new Promise((resolve) => handlers[0](message, null, (reply) => resolve({ ...reply })));
}

const GAME_URL = "https://dl3.vimm.net/?mediaId=9&token=t";

test("download-find answers with the id of the download the page started", async () => {
  const queries = [];
  const ask = loadMessages({ routeDownloads: true }, {
    search: async (query) => (queries.push(query), [{ id: 7 }]),
  });
  assert.deepEqual(await ask({ type: "download-find", url: GAME_URL }), { ok: true, id: 7 });
  assert.deepEqual(queries.map((query) => query.url), [GAME_URL]);
});

test("download-find answers with no id while the browser lists nothing", async () => {
  const ask = loadMessages({ routeDownloads: true }, { search: async () => [] });
  assert.deepEqual(await ask({ type: "download-find", url: GAME_URL }), { ok: true, id: null });
});

test("download-find refuses when the option is off, the permission is missing or the host is foreign", async () => {
  const downloads = { search: async () => [{ id: 1 }] };
  const off = await loadMessages({}, downloads)({ type: "download-find", url: GAME_URL });
  assert.equal(off.ok, false);
  const missing = await loadMessages({ routeDownloads: true }, undefined)({
    type: "download-find",
    url: GAME_URL,
  });
  assert.equal(missing.ok, false);
  const foreign = await loadMessages({ routeDownloads: true }, downloads)({
    type: "download-find",
    url: "https://example.com/?mediaId=9&token=t",
  });
  assert.equal(foreign.ok, false);
});

test("download-state reports the state and the saved path", async () => {
  const ask = loadMessages({}, {
    search: async ({ id }) =>
      id === 7 ? [{ state: "complete", filename: "/home/user/Downloads/romledger/Game.zip" }] : [],
  });
  assert.deepEqual(await ask({ type: "download-state", id: 7 }), {
    ok: true,
    state: "complete",
    filename: "/home/user/Downloads/romledger/Game.zip",
    reason: "",
  });
  assert.equal((await ask({ type: "download-state", id: 8 })).ok, false);
});

test("download-cancel cancels the download", async () => {
  const cancelled = [];
  const ask = loadMessages({}, { cancel: async (id) => cancelled.push(id) });
  assert.deepEqual(await ask({ type: "download-cancel", id: 7 }), { ok: true });
  assert.deepEqual(cancelled, [7]);
});
