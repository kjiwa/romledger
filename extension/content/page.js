const page = (() => {
  "use strict";

  const api = globalThis.browser ?? globalThis.chrome;
  const CONCURRENCY = 6;
  const status = { recognized: true, detail: "" };

  function ask(message) {
    return api.runtime.sendMessage(message);
  }

  function setStatus(recognized, detail) {
    status.recognized = recognized;
    status.detail = detail;
  }

  api.runtime.onMessage.addListener((message, _sender, respond) => {
    if (message.type === "page-status") {
      respond({ ...status });
    }
  });

  function badge(text, kind, title) {
    const element = document.createElement("span");
    element.className = "romledger-badge";
    element.dataset.kind = kind;
    element.textContent = text;
    if (title) {
      element.title = title;
    }
    return element;
  }

  function matchBadge(match) {
    const { text, kind, approximate } = romledger.describe(match);
    const title = approximate
      ? `Matched by title as ${match.game}. Check the region and version.`
      : match.game || "";
    return badge(text, kind, title);
  }

  function panel(heading) {
    const element = document.createElement("aside");
    element.className = "romledger-panel";
    element.setAttribute("aria-label", "romledger");
    const title = document.createElement("strong");
    title.textContent = heading;
    element.append(title);
    document.body.append(element);
    return element;
  }

  function row(label, node) {
    const element = document.createElement("div");
    element.className = "romledger-row";
    const name = document.createElement("span");
    name.className = "romledger-name";
    name.textContent = label;
    element.append(name, node);
    return element;
  }

  async function forEachLimited(items, work) {
    const queue = [...items];
    const workers = Array.from({ length: CONCURRENCY }, async () => {
      while (queue.length) {
        await work(queue.shift());
      }
    });
    await Promise.all(workers);
  }

  function failure(reply) {
    return badge("romledger unavailable", "error", reply.error);
  }

  function failurePanel(reply) {
    panel("romledger").append(row(reply.error, failure(reply)));
  }

  return { ask, setStatus, badge, matchBadge, panel, row, forEachLimited, failure, failurePanel };
})();
