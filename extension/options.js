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

function report(element, text, kind) {
  element.textContent = text;
  element.dataset.kind = kind;
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
    gap.disabled = !route.checked;
  } else {
    document.getElementById("downloads-unsupported").hidden = false;
  }
  await test();
}

async function test() {
  check.disabled = true;
  check.textContent = "Checking...";
  const reply = await api.runtime
    .sendMessage({ type: "platforms" })
    .catch(() => ({ ok: false, error: "The extension could not reach its background worker." }));
  check.disabled = false;
  check.textContent = "Check connection";
  if (reply.ok) {
    const count = reply.data.filter((platform) => platform.tracked).length;
    report(result, `Connected. ${count} ${count === 1 ? "platform has" : "platforms have"} games.`, "ok");
  } else {
    report(result, reply.error, "error");
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
    report(routeResult, error.message, "error");
    gap.disabled = !route.checked;
    return;
  }
  gap.disabled = !enabled;
  report(
    routeResult,
    enabled
      ? "Vimm's Lair downloads go to Downloads/romledger."
      : "Downloads are left where the browser puts them.",
    "ok",
  );
}

async function resetGap(message) {
  const saved = await api.storage.local.get(GAP_KEY);
  gap.value = romledger.gapSeconds(saved[GAP_KEY]);
  gap.setAttribute("aria-invalid", "true");
  report(gapResult, message, "error");
}

async function saveGap() {
  const seconds = Number(gap.value);
  const valid =
    gap.value.trim() !== "" &&
    Number.isFinite(seconds) &&
    seconds >= romledger.MIN_GAP_SECONDS &&
    seconds <= romledger.MAX_GAP_SECONDS;
  if (!valid) {
    await resetGap(`Enter a number of seconds from ${range()}.`);
    return;
  }
  try {
    await api.storage.local.set({ [GAP_KEY]: seconds });
  } catch (error) {
    await resetGap(error.message);
    return;
  }
  gap.removeAttribute("aria-invalid");
  report(gapResult, `Saved. Downloads start at least ${seconds} seconds apart.`, "ok");
}

check.addEventListener("click", test);
gap.addEventListener("change", saveGap);
route.addEventListener("change", toggleRoute);
load();
