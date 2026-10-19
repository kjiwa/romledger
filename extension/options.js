"use strict";

const api = globalThis.browser ?? globalThis.chrome;
const result = document.getElementById("result");
const check = document.getElementById("check");
const route = document.getElementById("route");
const routeResult = document.getElementById("route-result");
const ROUTE_KEY = "routeDownloads";
const DOWNLOADS = { permissions: ["downloads"] };

function show(text, kind) {
  result.textContent = text;
  result.dataset.kind = kind;
}

async function load() {
  const stored = await api.storage.local.get(ROUTE_KEY);
  if (typeof api.runtime.getBrowserInfo !== "function") {
    document.getElementById("route-field").hidden = false;
    route.checked = stored[ROUTE_KEY] === true && (await api.permissions.contains(DOWNLOADS));
  }
  await test();
}

async function test() {
  const reply = await api.runtime.sendMessage({ type: "platforms" });
  if (reply.ok) {
    const count = reply.data.filter((platform) => platform.tracked).length;
    show(`Connected. ${count} platform(s) with games.`, "ok");
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

check.addEventListener("click", test);
route.addEventListener("change", toggleRoute);
load();
