"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const romledger = require("../../extension/lib/romledger.js");

const SOURCE = fs.readFileSync(path.join(__dirname, "../../extension/options.js"), "utf8");

function load({ stored = {}, grant = true, revoke = true, failSet = false, reply, reject = false } = {}) {
  const elements = {};
  const element = (id) => {
    elements[id] ??= {
      id,
      listeners: {},
      attributes: {},
      value: "",
      checked: false,
      hidden: true,
      dataset: {},
    };
    elements[id].setAttribute = (name, value) => {
      elements[id].attributes[name] = value;
    };
    elements[id].removeAttribute = (name) => {
      delete elements[id].attributes[name];
    };
    elements[id].addEventListener = (type, listener) => {
      elements[id].listeners[type] = listener;
    };
    return elements[id];
  };
  const local = { ...stored };
  const chrome = {
    storage: {
      local: {
        get: async () => ({ ...local }),
        set: async (values) => {
          if (failSet) {
            throw new Error("quota");
          }
          Object.assign(local, values);
        },
      },
    },
    permissions: {
      request: async () => grant,
      remove: async () => revoke,
      contains: async () => true,
    },
    runtime: {
      sendMessage: async () => {
        if (reject) {
          throw new Error("no worker");
        }
        return reply ?? { ok: true, data: [] };
      },
    },
  };
  const document = { getElementById: element };
  vm.runInNewContext(SOURCE, { chrome, document, URL, romledger });
  return { elements, local };
}

async function settle() {
  await new Promise((resolve) => setImmediate(resolve));
}

async function toggle(options, checked) {
  const state = load(options);
  await settle();
  state.elements.route.checked = checked;
  await state.elements.route.listeners.change();
  return state;
}

test("ticking the option stores the flag once the permission is granted", async () => {
  const { elements, local } = await toggle({}, true);
  assert.equal(local.routeDownloads, true);
  assert.equal(elements.route.checked, true);
  assert.equal(elements["route-result"].dataset.kind, "ok");
});

test("a refused permission leaves the option off and says so", async () => {
  const { elements, local } = await toggle({ grant: false }, true);
  assert.equal(local.routeDownloads, undefined);
  assert.equal(elements.route.checked, false);
  assert.equal(elements["route-result"].dataset.kind, "error");
});

test("unticking removes the permission and then clears the flag", async () => {
  const { elements, local } = await toggle({ stored: { routeDownloads: true } }, false);
  assert.equal(local.routeDownloads, false);
  assert.equal(elements["route-result"].dataset.kind, "ok");
});

test("a permission that cannot be removed keeps the option on and reports an error", async () => {
  const { elements, local } = await toggle(
    { stored: { routeDownloads: true }, revoke: false },
    false,
  );
  assert.equal(local.routeDownloads, true);
  assert.equal(elements.route.checked, true);
  assert.equal(elements["route-result"].dataset.kind, "error");
});

test("a failed save keeps the checkbox at what was saved and reports an error", async () => {
  const { elements } = await toggle({ stored: { routeDownloads: true }, failSet: true }, false);
  assert.equal(elements.route.checked, true);
  assert.equal(elements["route-result"].dataset.kind, "error");
  assert.match(elements["route-result"].textContent, /quota/);
});

test("opening the page checks the connection and counts platforms with games", async () => {
  const reply = { ok: true, data: [{ tracked: true }, { tracked: false }, { tracked: true }] };
  const { elements } = load({ reply });
  await settle();
  assert.equal(elements.result.textContent, "Connected. 2 platforms have games.");
  assert.equal(elements.result.dataset.kind, "ok");
});

test("a single platform with games is worded in the singular", async () => {
  const { elements } = load({ reply: { ok: true, data: [{ tracked: true }] } });
  await settle();
  assert.equal(elements.result.textContent, "Connected. 1 platform has games.");
});

test("a worker that cannot be reached is shown as an error and the button recovers", async () => {
  const { elements } = load({ reject: true });
  await settle();
  assert.equal(elements.result.dataset.kind, "error");
  assert.match(elements.result.textContent, /background worker/);
  assert.equal(elements.check.disabled, false);
  assert.equal(elements.check.textContent, "Check connection");
});

test("a host that cannot be reached is shown as an error", async () => {
  const { elements } = load({ reply: { ok: false, error: "Run romledger extension install." } });
  await settle();
  assert.equal(elements.result.textContent, "Run romledger extension install.");
  assert.equal(elements.result.dataset.kind, "error");
});

test("the button checks again", async () => {
  const state = load({ reply: { ok: false, error: "down" } });
  await settle();
  assert.equal(state.elements.result.dataset.kind, "error");
  await state.elements.check.listeners.click();
  assert.equal(state.elements.result.textContent, "down");
});

test("the gap field shows the saved value within the allowed range", async () => {
  const { elements } = load({ stored: { gapSeconds: 45 } });
  await settle();
  assert.equal(elements.gap.value, 45);
  assert.equal(elements.gap.min, 15);
  assert.equal(elements.gap.max, 600);
  assert.equal(elements["gap-field"].hidden, false);
  assert.match(elements["gap-help"].textContent, /15 to 600 seconds/);
});

test("the gap field starts at the default and keeps an out-of-range saved value in range", async () => {
  const fresh = load({});
  await settle();
  assert.equal(fresh.elements.gap.value, 15);
  const wild = load({ stored: { gapSeconds: 1 } });
  await settle();
  assert.equal(wild.elements.gap.value, 15);
});

async function change(value, options = {}) {
  const state = load(options);
  await settle();
  state.elements.gap.value = value;
  await state.elements.gap.listeners.change();
  return state;
}

test("a valid gap is saved", async () => {
  const { elements, local } = await change("60");
  assert.equal(local.gapSeconds, 60);
  assert.equal(elements["gap-result"].dataset.kind, "ok");
  assert.match(elements["gap-result"].textContent, /at least 60 seconds apart/);
});

test("a gap outside the range or not a number is refused and the field is reset", async () => {
  for (const value of ["5", "601", "", "soon"]) {
    const { elements, local } = await change(value, { stored: { gapSeconds: 30 } });
    assert.equal(local.gapSeconds, 30, value);
    assert.equal(elements.gap.value, 30, value);
    assert.equal(elements["gap-result"].dataset.kind, "error", value);
    assert.match(elements["gap-result"].textContent, /from 15 to 600/);
  }
});

test("a gap that cannot be stored is reported and the field is reset", async () => {
  const { elements } = await change("60", { stored: { gapSeconds: 30 }, failSet: true });
  assert.equal(elements.gap.value, 30);
  assert.equal(elements["gap-result"].dataset.kind, "error");
  assert.match(elements["gap-result"].textContent, /quota/);
});

test("the gap field is disabled until downloads are on, and a refused gap is flagged invalid", async () => {
  const off = load({});
  await settle();
  assert.equal(off.elements.gap.disabled, true);
  const on = await toggle({}, true);
  assert.equal(on.elements.gap.disabled, false);
  const { elements } = await change("5", { stored: { gapSeconds: 30 } });
  assert.equal(elements.gap.attributes["aria-invalid"], "true");
});
