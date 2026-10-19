const page = (() => {
  "use strict";

  const api = globalThis.browser ?? globalThis.chrome;
  const CONCURRENCY = 6;
  const status = { recognized: true, detail: "" };
  let panels = 0;
  let failureBox = null;

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

  function button(label, onClick, variant) {
    const element = document.createElement("button");
    element.type = "button";
    element.className = "romledger-button";
    if (variant) {
      element.dataset.variant = variant;
    }
    element.textContent = label;
    element.addEventListener("click", onClick);
    return element;
  }

  function panel(heading) {
    const element = document.createElement("aside");
    element.className = "romledger-panel";
    const head = document.createElement("div");
    head.className = "romledger-panel-head";
    const title = document.createElement("strong");
    title.id = `romledger-panel-${panels}`;
    panels += 1;
    title.setAttribute("role", "heading");
    title.setAttribute("aria-level", "2");
    title.textContent = heading;
    element.setAttribute("aria-labelledby", title.id);
    const close = button("Close", () => element.remove());
    close.setAttribute("aria-label", `Close ${heading}`);
    head.append(title, close);
    element.append(head);
    document.body.append(element);
    return element;
  }

  function notice(text, kind) {
    const element = document.createElement("p");
    element.className = "romledger-notice";
    element.setAttribute("role", kind === "error" ? "alert" : "status");
    if (kind) {
      element.dataset.kind = kind;
    }
    element.textContent = text;
    return element;
  }

  function row(label, ...nodes) {
    const element = document.createElement("div");
    element.className = "romledger-row";
    const name = document.createElement("span");
    name.className = "romledger-name";
    name.textContent = label;
    element.append(name, ...nodes);
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
    const box = panel("romledger");
    box.append(notice(reply.error, "error"));
    return box;
  }

  function reportOnce(reply) {
    if (!failureBox?.isConnected) {
      failureBox = failurePanel(reply);
    }
  }

  async function run(work) {
    try {
      await work();
    } catch (error) {
      setStatus(false, `romledger could not annotate this page: ${error.message}`);
    }
  }

  return {
    run,
    ask,
    setStatus,
    badge,
    matchBadge,
    panel,
    notice,
    row,
    button,
    forEachLimited,
    failure,
    failurePanel,
    reportOnce,
  };
})();
