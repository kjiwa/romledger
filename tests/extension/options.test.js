"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const SOURCE = fs.readFileSync(path.join(__dirname, "../../extension/options.js"), "utf8");

function load({ stored = {}, grant = true, revoke = true, failSet = false }) {
  const elements = {};
  const element = (id) => {
    elements[id] ??= { id, listeners: {}, value: "", checked: false, hidden: true, dataset: {} };
    elements[id].addEventListener = (type, listener) => {
      elements[id].listeners[type] = listener;
    };
    return elements[id];
  };
  const form = element("form");
  form.url = { value: "" };
  form.token = { value: "" };
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
    runtime: {},
  };
  const document = { getElementById: element };
  vm.runInNewContext(SOURCE, { chrome, document, URL });
  return { elements, local };
}

async function toggle(options, checked) {
  const state = load(options);
  await new Promise((resolve) => setImmediate(resolve));
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
