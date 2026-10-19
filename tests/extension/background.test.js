"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const romledger = require("../../extension/lib/romledger.js");
romledger.register(require("../../extension/sites/vimm.js"));

const SOURCE = fs.readFileSync(path.join(__dirname, "../../extension/background.js"), "utf8");
const VIMM = { url: "https://dl3.vimm.net/", filename: "/home/user/Downloads/Game (USA).zip" };

function fakePort() {
  const listeners = { message: [], disconnect: [] };
  return {
    sent: [],
    postMessage(message) {
      this.sent.push(message);
    },
    onMessage: { addListener: (listener) => listeners.message.push(listener) },
    onDisconnect: { addListener: (listener) => listeners.disconnect.push(listener) },
    reply(message) {
      listeners.message.forEach((listener) => listener(message));
    },
    close(error) {
      listeners.disconnect.forEach((listener) => listener({ error }));
    },
  };
}

function load(stored, downloads = true, extra = {}) {
  const added = [];
  const local = { ...stored };
  const ports = [];
  const handlers = [];
  const opened = [];
  const chrome = {
    storage: {
      local: {
        get: async () => ({ ...local }),
        set: async (values) => Object.assign(local, values),
        remove: async (keys) => keys.forEach((key) => delete local[key]),
      },
    },
    runtime: {
      onMessage: { addListener: (handler) => handlers.push(handler) },
      openOptionsPage: async () => opened.push(true),
      connectNative: (name) => {
        const port = fakePort();
        port.name = name;
        ports.push(port);
        return port;
      },
    },
    permissions: { onAdded: { addListener: (listener) => added.push(listener) } },
  };
  const listeners = [];
  const changed = [];
  if (downloads) {
    chrome.downloads = {
      onDeterminingFilename: { addListener: (l) => listeners.push(l) },
      onChanged: { addListener: (l) => changed.push(l) },
      ...extra,
    };
  }
  vm.runInNewContext(SOURCE, { chrome, romledger, URLSearchParams });
  const ask = (message) =>
    new Promise((resolve) => handlers[0](message, null, (reply) => resolve({ ...reply })));
  return { listeners, added, changed, local, ports, ask, opened };
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
  const { ask } = load(stored, downloads !== undefined, downloads);
  return ask;
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

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

async function settle() {
  await new Promise((resolve) => setImmediate(resolve));
}

test("lookups and the platform list go to the host over one long-lived port", async () => {
  const { ask, ports } = load({});
  const platforms = ask({ type: "platforms" });
  const bySha1 = ask({ type: "lookup-sha1", sha1: "ab" });
  const byName = ask({ type: "lookup-name", name: "Game (USA)", platform: "snes" });
  assert.equal(ports.length, 1);
  assert.equal(ports[0].name, "io.github.kjiwa.romledger");
  assert.deepEqual(plain(ports[0].sent), [
    { type: "platforms", id: 1 },
    { type: "lookup", sha1: "ab", id: 2 },
    { type: "lookup", name: "Game (USA)", platform: "snes", regions: [], id: 3 },
  ]);
  ports[0].reply({ id: 2, ok: true, data: { matches: [] } });
  ports[0].reply({ id: 1, ok: true, data: [{ slug: "nes" }] });
  ports[0].reply({ id: 3, ok: false, error: "unknown platform 'snes'" });
  assert.deepEqual(await platforms, { ok: true, data: [{ slug: "nes" }] });
  assert.deepEqual(await bySha1, { ok: true, data: { matches: [] } });
  assert.deepEqual(await byName, { ok: false, error: "unknown platform 'snes'" });
});

test("a missing host says to run romledger extension install", async () => {
  const { ask, ports } = load({});
  const reply = ask({ type: "platforms" });
  ports[0].close({ message: "Specified native messaging host not found." });
  assert.deepEqual(await reply, {
    ok: false,
    error: 'Run "romledger extension install", then reload the extension.',
  });
});

test("a host that stops is reported and the next request starts a new one", async () => {
  const { ask, ports } = load({});
  const first = ask({ type: "platforms" });
  ports[0].close({ message: "exited with code 1" });
  assert.match((await first).error, /The romledger host stopped: exited with code 1\./);
  const second = ask({ type: "platforms" });
  assert.equal(ports.length, 2);
  ports[1].reply({ id: 2, ok: true, data: [] });
  assert.equal((await second).ok, true);
});

test("a host that stops without a reason still says so", async () => {
  const { ask, ports } = load({});
  const reply = ask({ type: "platforms" });
  ports[0].close(undefined);
  assert.match((await reply).error, /no reason given/);
});

test("a port that cannot be written to is an error reply", async () => {
  const { ask, ports } = load({});
  ask({ type: "platforms" });
  ports[0].postMessage = () => {
    throw new Error("Native host has exited.");
  };
  assert.match((await ask({ type: "platforms" })).error, /The romledger host stopped/);
});

test("an unknown message type is refused", async () => {
  assert.deepEqual(await load({}).ask({ type: "bogus" }), {
    ok: false,
    error: "Unknown request bogus.",
  });
});

test("a finished Vimm download is imported and the outcome is kept for the popup", async () => {
  const done = { id: 7, url: "https://dl3.vimm.net/x", filename: "/home/user/Downloads/romledger/G.zip" };
  const { changed, ports, local } = load({ routeDownloads: true }, true, {
    search: async () => [done],
  });
  changed[0]({ id: 7, state: { current: "complete" } });
  await settle();
  assert.deepEqual(plain(ports[0].sent), [
    { type: "import", path: "/home/user/Downloads/romledger/G.zip", id: 1 },
  ]);
  ports[0].reply({ id: 1, ok: true, data: { lines: ["moved snes 1"], failures: [] } });
  await settle();
  assert.deepEqual(
    { ...local.lastImport, at: 0 },
    { at: 0, lines: ["moved snes 1"], failures: [] },
  );
});

test("a failed import is kept as an error", async () => {
  const done = { id: 7, url: "https://dl3.vimm.net/x", filename: "/x/G.zip" };
  const { changed, ports, local } = load({ routeDownloads: true }, true, {
    search: async () => [done],
  });
  changed[0]({ id: 7, state: { current: "complete" } });
  await settle();
  ports[0].reply({ id: 1, ok: false, error: "/x is not an inbox." });
  await settle();
  assert.equal(local.lastImport.error, "/x is not an inbox.");
});

test("downloads that are unfinished, foreign or unrouted are not imported", async () => {
  const foreign = { id: 7, url: "https://example.com/x", filename: "/x/G.zip" };
  const search = async () => [foreign];
  const routed = load({ routeDownloads: true }, true, { search });
  routed.changed[0]({ id: 7, state: { current: "in_progress" } });
  routed.changed[0]({ id: 7, filename: { current: "/x" } });
  routed.changed[0]({ id: 7, state: { current: "complete" } });
  await settle();
  assert.equal(routed.ports.length, 0);
  const off = load({}, true, { search });
  off.changed[0]({ id: 7, state: { current: "complete" } });
  await settle();
  assert.equal(off.ports.length, 0);
  const gone = load({ routeDownloads: true }, true, { search: async () => [] });
  gone.changed[0]({ id: 7, state: { current: "complete" } });
  await settle();
  assert.equal(gone.ports.length, 0);
});

test("the url and token of the old HTTP setup are forgotten", async () => {
  const { local } = load({ url: "http://127.0.0.1:8730", token: "t", routeDownloads: true });
  await settle();
  assert.deepEqual(local, { routeDownloads: true });
});

test("open-options opens the options page", async () => {
  const { ask, opened } = load({});
  assert.deepEqual(await ask({ type: "open-options" }), { ok: true });
  assert.equal(opened.length, 1);
});
