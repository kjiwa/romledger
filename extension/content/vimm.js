page.run(async () => {
  "use strict";

  const GAME_PATH = /^\/vault\/\d+\/?$/;
  const STOPPED = { ok: false, stopped: true, error: "Stopped." };
  const POLL_MS = 3000;
  const PAUSED =
    "Vimm's Lair did not offer a download. Open a game page, pass the check, then press Resume.";

  async function lookupDisc(disc, slug) {
    const byHash = await page.ask({ type: "lookup-sha1", sha1: disc.sha1 });
    if (!byHash.ok) {
      return byHash;
    }
    const first = byHash.data.matches[0] || { state: "unknown" };
    if (first.state !== "unknown" || !slug) {
      return { ok: true, match: first };
    }
    const byName = await page.ask({ type: "lookup-name", name: disc.name, platform: slug });
    return byName.ok ? { ok: true, match: romledger.best(byName.data.matches, first) } : byName;
  }

  async function annotateGame() {
    const discs = romledger.parseAllMedia(
      [...document.scripts].map((script) => script.textContent).find((text) => text.includes("allMedia")) || "",
    );
    if (!discs) {
      page.setStatus(false, "Vimm's Lair page layout not recognized: the allMedia data is missing.");
      return;
    }
    const platforms = await page.ask({ type: "platforms" });
    if (!platforms.ok) {
      page.failurePanel(platforms);
      return;
    }
    const slug = romledger.slugFor(
      platforms.data,
      "vimm",
      romledger.vimmSystemFromTitle(document.title),
    );
    const panel = page.panel("romledger");
    for (const disc of discs) {
      const result = await lookupDisc(disc, slug);
      panel.append(page.row(disc.name, result.ok ? page.matchBadge(result.match) : page.failure(result)));
    }
  }

  function sleep(ms) {
    return new Promise((done) => setTimeout(done, ms));
  }

  function note(text) {
    const element = document.createElement("span");
    element.className = "romledger-name";
    element.textContent = text;
    return element;
  }

  async function downloadUrlFor(gameUrl) {
    const response = await fetch(gameUrl, { credentials: "same-origin" });
    if (!response.ok) {
      return null;
    }
    const doc = new DOMParser().parseFromString(await response.text(), "text/html");
    return romledger.vimmDownloadUrl(doc, gameUrl);
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

  async function startDownload(entry, queue, controls) {
    while (!queue.stopped) {
      const url = await downloadUrlFor(entry.url);
      if (url) {
        return page.ask({ type: "download", url });
      }
      await controls.pause(queue);
    }
    return STOPPED;
  }

  async function download(entry, queue, controls) {
    try {
      const started = await startDownload(entry, queue, controls);
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
    return page.row(entry.title, page.badge("Failed", "error", error));
  }

  async function downloadQueue(ready, queue, controls) {
    for (const [index, entry] of ready.entries()) {
      if (queue.stopped) {
        break;
      }
      controls.progress(`Downloading ${index + 1} of ${ready.length}: ${entry.title}`);
      const outcome = await download(entry, queue, controls);
      if (outcome.stopped) {
        break;
      }
      controls.append(outcomeRow(entry, outcome));
      if (outcome.fatal) {
        queue.stopped = true;
      }
    }
    controls.progress(queue.stopped ? "Stopped." : "Finished.");
  }

  function queueControls(panel, queue) {
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
        progress.textContent = PAUSED;
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

  function setUpQueue(entries) {
    const { ready, approximate } = romledger.queueable(entries);
    if (!ready.length) {
      return;
    }
    const queue = { stopped: false, resume: null };
    const panel = page.panel("Missing games");
    const controls = queueControls(panel, queue);
    const caution = approximate
      ? ` ${approximate} matched by title; check their region and version.`
      : "";
    controls.progress(`${ready.length} missing.${caution}`);
    const start = page.button(`Download ${ready.length} missing`, async () => {
      start.hidden = true;
      controls.showStop();
      await downloadQueue(ready, queue, controls);
      controls.hideStop();
    });
    panel.append(start);
  }

  async function annotateList(system) {
    const links = [...document.querySelectorAll("td a[href]")].filter((link) =>
      GAME_PATH.test(new URL(link.href).pathname),
    );
    if (!links.length) {
      page.setStatus(false, "Vimm's Lair page layout not recognized: no game links found.");
      return;
    }
    const platforms = await page.ask({ type: "platforms" });
    if (!platforms.ok) {
      page.failurePanel(platforms);
      return;
    }
    const slug = romledger.slugFor(platforms.data, "vimm", system);
    if (!slug) {
      page.setStatus(true, `romledger does not track ${system || "this system"}.`);
      return;
    }
    const matches = new Map();
    await page.forEachLimited(links, async (link) => {
      const reply = await page.ask({
        type: "lookup-name",
        name: link.textContent.trim(),
        platform: slug,
        regions: romledger.regionsOf(link.closest("tr")),
      });
      if (reply.ok) {
        matches.set(link, romledger.best(reply.data.matches));
      }
      link.after(" ", reply.ok ? page.matchBadge(matches.get(link)) : page.failure(reply));
    });
    setUpQueue(
      links
        .filter((link) => matches.has(link))
        .map((link) => ({ title: link.textContent.trim(), url: link.href, match: matches.get(link) })),
    );
  }

  const listSystem = romledger.vimmListSystem(location.href);
  if (GAME_PATH.test(location.pathname)) {
    await annotateGame();
  } else if (listSystem) {
    await annotateList(listSystem);
  }
});
