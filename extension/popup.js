"use strict";

const api = globalThis.browser ?? globalThis.chrome;

function platformItem(platform) {
  const item = document.createElement("li");
  const name = document.createElement("span");
  name.textContent = platform.name;
  const meter = document.createElement("progress");
  meter.max = 100;
  meter.value = platform.percent ?? 0;
  const text = document.createElement("span");
  text.className = "muted";
  text.textContent = romledger.progress(platform);
  meter.setAttribute("aria-label", `${platform.name} progress`);
  meter.setAttribute("aria-valuetext", text.textContent);
  item.append(name, meter, text);
  return item;
}

function showNotice(id, text, kind) {
  const note = document.getElementById(id);
  note.textContent = text;
  note.dataset.kind = kind;
  note.hidden = false;
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
    showNotice(
      "page",
      reply.detail || "Page layout not recognized.",
      reply.recognized ? "info" : "error",
    );
  }
}

async function showLastImport() {
  const stored = await api.storage.local.get("lastImport");
  const last = stored.lastImport;
  if (!last) {
    return;
  }
  const failed = Boolean(last.error) || (last.failures || []).length > 0;
  const when = last.at ? ` ${romledger.ago(last.at, Date.now())}` : "";
  showNotice(
    "import",
    failed
      ? `Last import failed${when}: ${last.error || last.failures.join("; ")}`
      : `Last import${when}: ${last.lines.join("; ")}`,
    failed ? "error" : "ok",
  );
}

async function main() {
  const reply = await api.runtime
    .sendMessage({ type: "platforms" })
    .catch(() => ({ ok: false, error: "The extension could not reach its background worker." }));
  if (reply.ok) {
    const tracked = reply.data.filter((platform) => platform.tracked);
    document.getElementById("platforms").replaceChildren(...tracked.map(platformItem));
    if (!tracked.length) {
      showNotice("empty", "No games yet. Put ROMs in an inbox and run romledger import.", "info");
    }
  } else {
    showNotice("error", reply.error, "error");
  }
  await showPageStatus();
  await showLastImport();
}

document.getElementById("options").addEventListener("click", () => {
  api.runtime.openOptionsPage();
  window.close();
});

main();
