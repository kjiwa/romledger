"use strict";

const api = globalThis.browser ?? globalThis.chrome;

function platformItem(platform) {
  const item = document.createElement("li");
  const name = document.createElement("span");
  name.textContent = platform.name;
  const meter = document.createElement("progress");
  meter.max = 100;
  meter.value = platform.percent ?? 0;
  meter.setAttribute("aria-label", `${platform.name} progress`);
  const text = document.createElement("span");
  text.className = "muted";
  text.textContent = romledger.progress(platform);
  item.append(name, meter, text);
  return item;
}

function showError(text) {
  const error = document.getElementById("error");
  error.textContent = text;
  error.hidden = false;
}

async function showPageStatus() {
  let reply;
  try {
    const [tab] = await api.tabs.query({ active: true, currentWindow: true });
    reply = await api.tabs.sendMessage(tab.id, { type: "page-status" });
  } catch {
    return;
  }
  if (reply && (!reply.recognized || reply.detail)) {
    const note = document.getElementById("page");
    note.textContent = reply.detail || "Page layout not recognized.";
    note.dataset.kind = reply.recognized ? "info" : "error";
    note.hidden = false;
  }
}

async function main() {
  const reply = await api.runtime
    .sendMessage({ type: "platforms" })
    .catch(() => ({ ok: false, error: "The extension could not reach its background worker." }));
  if (reply.ok) {
    const tracked = reply.data.filter((platform) => platform.tracked);
    document.getElementById("platforms").replaceChildren(...tracked.map(platformItem));
    if (!tracked.length) {
      showError("No games yet. Put ROMs in an inbox and run romledger import.");
    }
  } else {
    showError(reply.error);
  }
  await showPageStatus();
}

main();
