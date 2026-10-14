"use strict";

const api = globalThis.browser ?? globalThis.chrome;
const form = document.getElementById("form");
const result = document.getElementById("result");
const route = document.getElementById("route");
const routeResult = document.getElementById("route-result");
const ROUTE_KEY = "routeDownloads";
const DOWNLOADS = { permissions: ["downloads"] };
const DEFAULT_URL = "http://127.0.0.1:8730";

function show(text, kind) {
  result.textContent = text;
  result.dataset.kind = kind;
}

async function load() {
  const stored = await api.storage.local.get(["url", "token", ROUTE_KEY]);
  if (typeof api.runtime.getBrowserInfo !== "function") {
    document.getElementById("route-field").hidden = false;
    route.checked = stored[ROUTE_KEY] === true && (await api.permissions.contains(DOWNLOADS));
  }
  form.url.value = stored.url || DEFAULT_URL;
  form.token.value = stored.token || "";
}

async function save(event) {
  event.preventDefault();
  const url = form.url.value.trim().replace(/\/+$/, "");
  let origin;
  try {
    origin = new URL(url).origin;
  } catch {
    origin = "null";
  }
  if (!/^https?:\/\//.test(origin)) {
    show("Enter the address with http:// or https://, such as http://127.0.0.1:8730.", "error");
    return;
  }
  const granted = await api.permissions.request({ origins: [`${origin}/*`] });
  if (!granted) {
    show("The browser did not allow access to that address.", "error");
    return;
  }
  await api.storage.local.set({ url, token: form.token.value.trim() });
  const reply = await api.runtime.sendMessage({ type: "platforms" });
  if (reply.ok) {
    show(`Connected. ${reply.data.length} platform(s) configured.`, "ok");
  } else {
    show(reply.error, "error");
  }
}

async function applyRoute(enabled) {
  if (enabled) {
    if (!(await api.permissions.request(DOWNLOADS))) {
      throw new Error("The browser did not allow access to downloads.");
    }
  } else if (!(await api.permissions.remove(DOWNLOADS))) {
    throw new Error("The browser did not give the downloads permission back.");
  }
  await api.storage.local.set({ [ROUTE_KEY]: enabled });
}

async function toggleRoute() {
  const enabled = route.checked;
  try {
    await applyRoute(enabled);
  } catch (error) {
    const saved = await api.storage.local.get(ROUTE_KEY);
    route.checked = saved[ROUTE_KEY] === true;
    routeResult.textContent = error.message;
    routeResult.dataset.kind = "error";
    return;
  }
  routeResult.textContent = enabled
    ? "Vimm's Lair downloads go to Downloads/romledger."
    : "Downloads are left where the browser puts them.";
  routeResult.dataset.kind = "ok";
}

form.addEventListener("submit", save);
route.addEventListener("change", toggleRoute);
load();
