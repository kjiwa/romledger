"use strict";

const api = globalThis.browser ?? globalThis.chrome;
const NOT_CONFIGURED = "Open the romledger options and enter the service URL and token.";

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

function route(message) {
  const query = new URLSearchParams();
  if (message.type === "platforms") {
    return call("/api/platforms");
  }
  if (message.type === "lookup-sha1") {
    query.set("sha1", message.sha1);
  } else if (message.type === "lookup-name") {
    query.set("name", message.name);
    query.set("platform", message.platform);
  } else {
    return Promise.resolve({ ok: false, error: `Unknown request ${message.type}.` });
  }
  return call(`/api/lookup?${query}`);
}

api.runtime.onMessage.addListener((message, _sender, respond) => {
  route(message).then(respond);
  return true;
});
