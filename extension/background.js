"use strict";

if (typeof importScripts === "function") {
  importScripts("lib/romledger.js", "sites/vimm.js");
}

const api = globalThis.browser ?? globalThis.chrome;
const HOST = "io.github.kjiwa.romledger";
const ROUTE_KEY = "routeDownloads";
const LAST_IMPORT_KEY = "lastImport";
const NOT_INSTALLED = 'Run "romledger extension install", then reload the extension.';
const DOWNLOADS_OFF = "Turn on the download option in the romledger options.";
const MISSING_HOST = /not found|forbidden|no such native application/i;

let port = null;
let nextId = 1;
const pending = new Map();

function hostError(reason) {
  return MISSING_HOST.test(reason)
    ? NOT_INSTALLED
    : `The romledger host stopped: ${reason || "no reason given"}.`;
}

function onReply(message) {
  const resolve = pending.get(message.id);
  if (resolve) {
    pending.delete(message.id);
    resolve(message.ok ? { ok: true, data: message.data } : { ok: false, error: message.error });
  }
}

function onDisconnect(closed) {
  const reason = closed?.error?.message ?? api.runtime.lastError?.message ?? "";
  port = null;
  for (const resolve of pending.values()) {
    resolve({ ok: false, error: hostError(reason) });
  }
  pending.clear();
}

function ask(request) {
  if (!port) {
    try {
      port = api.runtime.connectNative(HOST);
    } catch (error) {
      return Promise.resolve({ ok: false, error: hostError(error.message) });
    }
    port.onMessage.addListener(onReply);
    port.onDisconnect.addListener(onDisconnect);
  }
  const id = nextId++;
  return new Promise((resolve) => {
    pending.set(id, resolve);
    try {
      port.postMessage({ ...request, id });
    } catch (error) {
      pending.delete(id);
      resolve({ ok: false, error: hostError(error.message) });
    }
  });
}

async function findDownload(url) {
  const downloads = globalThis.chrome?.downloads;
  const stored = await api.storage.local.get(ROUTE_KEY);
  if (!downloads?.search || stored[ROUTE_KEY] !== true) {
    return { ok: false, error: DOWNLOADS_OFF };
  }
  if (!romledger.isSiteDownload({ url })) {
    return { ok: false, error: "Refused a download that is not from a supported site." };
  }
  try {
    const [item] = await downloads.search({ url });
    return { ok: true, id: item ? item.id : null };
  } catch (error) {
    return { ok: false, error: error.message };
  }
}

async function cancelDownload(id) {
  const downloads = globalThis.chrome?.downloads;
  if (!downloads?.cancel) {
    return { ok: false, error: DOWNLOADS_OFF };
  }
  try {
    await downloads.cancel(id);
    return { ok: true };
  } catch (error) {
    return { ok: false, error: error.message };
  }
}

async function downloadState(id) {
  const downloads = globalThis.chrome?.downloads;
  if (!downloads?.search) {
    return { ok: false, error: DOWNLOADS_OFF };
  }
  const [item] = await downloads.search({ id });
  if (!item) {
    return { ok: false, error: "The browser no longer lists this download." };
  }
  return { ok: true, state: item.state, filename: item.filename, reason: item.error || "" };
}

function route(message) {
  if (message.type === "download-find") {
    return findDownload(message.url);
  }
  if (message.type === "download-cancel") {
    return cancelDownload(message.id);
  }
  if (message.type === "download-state") {
    return downloadState(message.id);
  }
  if (message.type === "open-options") {
    return api.runtime.openOptionsPage().then(
      () => ({ ok: true }),
      (error) => ({ ok: false, error: error.message }),
    );
  }
  if (message.type === "platforms") {
    return ask({ type: "platforms" });
  }
  if (message.type === "lookup-sha1") {
    return ask({ type: "lookup", sha1: message.sha1 });
  }
  if (message.type === "lookup-name") {
    return ask({
      type: "lookup",
      name: message.name,
      platform: message.platform,
      regions: message.regions || [],
    });
  }
  return Promise.resolve({ ok: false, error: `Unknown request ${message.type}.` });
}

api.runtime.onMessage.addListener((message, _sender, respond) => {
  route(message).then(respond);
  return true;
});

async function routeTarget(item) {
  const stored = await api.storage.local.get(ROUTE_KEY);
  return stored[ROUTE_KEY] === true ? romledger.downloadTarget(item) : null;
}

function onDeterminingFilename(item, suggest) {
  if (!romledger.isSiteDownload(item)) {
    suggest();
    return;
  }
  routeTarget(item).then((filename) => {
    if (filename === null) {
      suggest();
    } else {
      suggest({ filename, conflictAction: "uniquify" });
    }
  }, () => suggest());
  return true;
}

async function importFinished(change) {
  if (change.state?.current !== "complete") {
    return;
  }
  const stored = await api.storage.local.get(ROUTE_KEY);
  if (stored[ROUTE_KEY] !== true) {
    return;
  }
  const [item] = await globalThis.chrome.downloads.search({ id: change.id });
  if (!item || !romledger.isSiteDownload(item)) {
    return;
  }
  const reply = await ask({ type: "import", path: item.filename });
  const outcome = reply.ok
    ? { lines: reply.data.lines, failures: reply.data.failures }
    : { error: reply.error };
  await api.storage.local.set({ [LAST_IMPORT_KEY]: { at: Date.now(), ...outcome } });
}

let listening = false;

function listenForDownloads() {
  const downloads = globalThis.chrome?.downloads;
  if (!listening && downloads?.onDeterminingFilename) {
    downloads.onDeterminingFilename.addListener(onDeterminingFilename);
    downloads.onChanged.addListener((change) => importFinished(change).catch(() => {}));
    listening = true;
  }
}

listenForDownloads();
api.permissions.onAdded.addListener(listenForDownloads);
api.storage.local.remove(["url", "token"]);
