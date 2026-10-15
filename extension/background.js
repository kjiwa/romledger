"use strict";

if (typeof importScripts === "function") {
  importScripts("lib/romledger.js");
}

const api = globalThis.browser ?? globalThis.chrome;
const ROUTE_KEY = "routeDownloads";
const NOT_CONFIGURED = "Open the romledger options and enter the service URL and token.";
const DOWNLOADS_OFF = "Turn on the Vimm's Lair download option in the romledger options.";

async function settings() {
  const stored = await api.storage.local.get(["url", "token"]);
  return { url: (stored.url || "").replace(/\/+$/, ""), token: stored.token || "" };
}

async function call(path) {
  const { url, token } = await settings();
  if (!url || !token) {
    return { ok: false, error: NOT_CONFIGURED };
  }
  let response;
  try {
    response = await fetch(`${url}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  } catch {
    return { ok: false, error: `Cannot reach ${url}. Is romledger serve running?` };
  }
  if (response.status === 401) {
    return { ok: false, error: "The service rejected the token. Check it in the options." };
  }
  if (!response.ok) {
    return { ok: false, error: `The service answered HTTP ${response.status}.` };
  }
  try {
    return { ok: true, data: await response.json() };
  } catch {
    return { ok: false, error: `The service at ${url} did not answer with JSON.` };
  }
}

async function startDownload(url) {
  const downloads = globalThis.chrome?.downloads;
  const stored = await api.storage.local.get(ROUTE_KEY);
  if (!downloads?.download || stored[ROUTE_KEY] !== true) {
    return { ok: false, fatal: true, error: DOWNLOADS_OFF };
  }
  if (!romledger.isVimmDownload({ url })) {
    return { ok: false, error: "Refused a download that is not from Vimm's Lair." };
  }
  try {
    return { ok: true, id: await downloads.download({ url }) };
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
  const query = new URLSearchParams();
  if (message.type === "download") {
    return startDownload(message.url);
  }
  if (message.type === "download-cancel") {
    return cancelDownload(message.id);
  }
  if (message.type === "download-state") {
    return downloadState(message.id);
  }
  if (message.type === "platforms") {
    return call("/api/platforms");
  }
  if (message.type === "lookup-sha1") {
    query.set("sha1", message.sha1);
  } else if (message.type === "lookup-name") {
    query.set("name", message.name);
    query.set("platform", message.platform);
    query.set("regions", (message.regions || []).join(","));
  } else {
    return Promise.resolve({ ok: false, error: `Unknown request ${message.type}.` });
  }
  return call(`/api/lookup?${query}`);
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
  if (!romledger.isVimmDownload(item)) {
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

let listening = false;

function listenForDownloads() {
  const downloads = globalThis.chrome?.downloads;
  if (!listening && downloads?.onDeterminingFilename) {
    downloads.onDeterminingFilename.addListener(onDeterminingFilename);
    listening = true;
  }
}

listenForDownloads();
api.permissions.onAdded.addListener(listenForDownloads);
