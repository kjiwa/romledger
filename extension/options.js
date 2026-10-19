"use strict";

const api = globalThis.browser ?? globalThis.chrome;
const result = document.getElementById("result");
const check = document.getElementById("check");
const route = document.getElementById("route");
const routeResult = document.getElementById("route-result");
const gap = document.getElementById("gap");
const gapResult = document.getElementById("gap-result");
const ROUTE_KEY = "routeDownloads";
const GAP_KEY = "gapSeconds";
const DOWNLOADS = { permissions: ["downloads"] };

function show(text, kind) {
  result.textContent = text;
  result.dataset.kind = kind;
}

function range() {
  return `${romledger.MIN_GAP_SECONDS} to ${romledger.MAX_GAP_SECONDS}`;
}

async function load() {
  const stored = await api.storage.local.get([ROUTE_KEY, GAP_KEY]);
  gap.min = romledger.MIN_GAP_SECONDS;
  gap.max = romledger.MAX_GAP_SECONDS;
  gap.value = romledger.gapSeconds(stored[GAP_KEY]);
  document.getElementById("gap-help").textContent =
    `The download queue starts a game this long after the last one, from ${range()} seconds. A longer wait is gentler on the site.`;
  if (typeof api.runtime.getBrowserInfo !== "function") {
    document.getElementById("route-field").hidden = false;
    document.getElementById("gap-field").hidden = false;
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

async function saveGap() {
  const seconds = Number(gap.value);
  const valid =
    gap.value.trim() !== "" &&
    Number.isFinite(seconds) &&
    seconds >= romledger.MIN_GAP_SECONDS &&
    seconds <= romledger.MAX_GAP_SECONDS;
  if (!valid) {
    const saved = await api.storage.local.get(GAP_KEY);
    gap.value = romledger.gapSeconds(saved[GAP_KEY]);
    gapResult.textContent = `Enter a number of seconds from ${range()}.`;
    gapResult.dataset.kind = "error";
    return;
  }
  try {
    await api.storage.local.set({ [GAP_KEY]: seconds });
  } catch (error) {
    const saved = await api.storage.local.get(GAP_KEY);
    gap.value = romledger.gapSeconds(saved[GAP_KEY]);
    gapResult.textContent = error.message;
    gapResult.dataset.kind = "error";
    return;
  }
  gapResult.textContent = `Saved. Downloads start at least ${seconds} seconds apart.`;
  gapResult.dataset.kind = "ok";
}

check.addEventListener("click", test);
gap.addEventListener("change", saveGap);
route.addEventListener("change", toggleRoute);
load();
