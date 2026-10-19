const missingQueue = (() => {
  "use strict";

  const api = globalThis.browser ?? globalThis.chrome;
  const GAP_KEY = "gapSeconds";
  const ROUTE_KEY = "routeDownloads";
  const STOPPED = { ok: false, stopped: true, error: "Stopped." };
  const POLL_MS = 3000;
  const FIND_MS = 1000;
  const FIND_TRIES = 30;

  function sleep(ms) {
    return new Promise((done) => setTimeout(done, ms));
  }

  function note(text) {
    const element = document.createElement("span");
    element.className = "romledger-name";
    element.textContent = text;
    return element;
  }

  async function downloadUrlFor(site, gameUrl) {
    const response = await fetch(gameUrl, { credentials: "same-origin" });
    if (response.status === 429) {
      throw new Error(site.messages.slowDown);
    }
    if (!response.ok) {
      return null;
    }
    const doc = new DOMParser().parseFromString(await response.text(), "text/html");
    return site.downloadUrl(doc, gameUrl);
  }

  async function awaitFinished(id, queue) {
    while (!queue.stopped) {
      const reply = await page.ask({ type: "download-state", id });
      if (!reply.ok || reply.state !== "in_progress") {
        return reply;
      }
      await sleep(POLL_MS);
    }
    await page.ask({ type: "download-cancel", id });
    return STOPPED;
  }

  async function findDownload(site, url, queue) {
    for (let tries = 0; tries < FIND_TRIES && !queue.stopped; tries += 1) {
      const reply = await page.ask({ type: "download-find", url });
      if (!reply.ok || reply.id !== null) {
        return reply;
      }
      await sleep(FIND_MS);
    }
    return queue.stopped ? STOPPED : { ok: false, error: `${site.label} did not start the download.` };
  }

  async function startFrom(site, url, queue) {
    const frame = document.createElement("iframe");
    frame.hidden = true;
    frame.src = url;
    document.body.append(frame);
    try {
      return await findDownload(site, url, queue);
    } finally {
      frame.remove();
    }
  }

  async function startDownload(site, entry, queue, controls) {
    while (!queue.stopped) {
      const url = await downloadUrlFor(site, entry.url);
      if (url) {
        return startFrom(site, url, queue);
      }
      await controls.pause(queue);
    }
    return STOPPED;
  }

  async function download(site, entry, queue, controls) {
    try {
      const started = await startDownload(site, entry, queue, controls);
      return started.ok ? await awaitFinished(started.id, queue) : started;
    } catch (error) {
      return { ok: false, error: error.message };
    }
  }

  function outcomeRow(entry, outcome) {
    if (outcome.ok && outcome.state === "complete") {
      return page.row(entry.title, note(outcome.filename));
    }
    const error = outcome.ok ? outcome.reason || outcome.state : outcome.error;
    return page.row(entry.title, page.badge("Failed", "error", error), note(error));
  }

  async function waitForGap(startedAt, queue) {
    while (!queue.stopped && Date.now() - startedAt < queue.gapMs) {
      await sleep(FIND_MS);
    }
  }

  async function downloadQueue(site, ready, queue, controls) {
    let failed = false;
    let startedAt = 0;
    for (const [index, entry] of ready.entries()) {
      await waitForGap(startedAt, queue);
      if (queue.stopped) {
        break;
      }
      startedAt = Date.now();
      controls.progress(`Downloading ${index + 1} of ${ready.length}: ${entry.title}`);
      const outcome = await download(site, entry, queue, controls);
      if (outcome.stopped) {
        break;
      }
      controls.append(outcomeRow(entry, outcome));
      if (!(outcome.ok && outcome.state === "complete")) {
        failed = true;
        queue.stopped = true;
      }
    }
    if (failed) {
      controls.progress("Stopped after a failed download.");
    } else {
      controls.progress(queue.stopped ? "Stopped." : "Finished.");
    }
  }

  function queueControls(site, panel, queue) {
    const progress = note("");
    progress.setAttribute("role", "status");
    const stop = page.button("Stop", () => {
      queue.stopped = true;
      queue.resume?.();
    });
    const resume = page.button("Resume", () => queue.resume());
    resume.hidden = true;
    stop.hidden = true;
    panel.append(progress, resume, stop);
    return {
      progress: (text) => {
        progress.textContent = text;
      },
      append: (node) => panel.append(node),
      showStop: () => {
        stop.hidden = false;
      },
      hideStop: () => {
        stop.hidden = true;
      },
      pause: (state) => {
        const waiting = progress.textContent;
        progress.textContent = site.messages.paused;
        resume.hidden = false;
        return new Promise((resolve) => {
          state.resume = () => {
            progress.textContent = waiting;
            resume.hidden = true;
            state.resume = null;
            resolve();
          };
        });
      },
    };
  }

  function offerOptions(panel, count, onEnabled) {
    const waiting = [
      page.notice(`${count} missing. Turn on downloading in the options to fetch them.`),
      page.button("Open options", () => page.ask({ type: "open-options" }), "primary"),
    ];
    panel.append(...waiting);
    const listener = (changes) => {
      if (changes[ROUTE_KEY]?.newValue === true) {
        api.storage.onChanged.removeListener(listener);
        waiting.forEach((node) => node.remove());
        onEnabled();
      }
    };
    api.storage.onChanged.addListener(listener);
  }

  async function offerQueue(site, panel, ready, approximate) {
    const stored = await api.storage.local.get(GAP_KEY);
    const queue = { stopped: false, resume: null, gapMs: romledger.gapSeconds(stored[GAP_KEY]) * 1000 };
    const controls = queueControls(site, panel, queue);
    const caution = approximate
      ? ` ${approximate} matched by title; check their region and version.`
      : "";
    controls.progress(`${ready.length} missing.${caution}`);
    const start = page.button(
      `Download ${ready.length} missing`,
      async () => {
        start.hidden = true;
        controls.showStop();
        await downloadQueue(site, ready, queue, controls);
        controls.hideStop();
      },
      "primary",
    );
    panel.append(start);
  }

  async function setUp(site, entries) {
    const { ready, approximate } = romledger.queueable(entries);
    if (!ready.length) {
      return;
    }
    const stored = await api.storage.local.get(ROUTE_KEY);
    const panel = page.panel("Missing games");
    if (stored[ROUTE_KEY] === true) {
      await offerQueue(site, panel, ready, approximate);
    } else {
      offerOptions(panel, ready.length, () => offerQueue(site, panel, ready, approximate));
    }
  }

  return { setUp };
})();
