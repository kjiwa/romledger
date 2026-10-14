"use strict";

const api = globalThis.browser ?? globalThis.chrome;
const form = document.getElementById("form");
const result = document.getElementById("result");

function show(text, kind) {
  result.textContent = text;
  result.dataset.kind = kind;
}

async function load() {
  const stored = await api.storage.local.get(["url", "token"]);
  form.url.value = stored.url || "";
  form.token.value = stored.token || "";
}

async function save(event) {
  event.preventDefault();
  const url = form.url.value.trim().replace(/\/+$/, "");
  const granted = await api.permissions.request({ origins: [`${new URL(url).origin}/*`] });
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

form.addEventListener("submit", save);
load();
