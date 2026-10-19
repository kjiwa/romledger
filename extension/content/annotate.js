page.run(async () => {
  "use strict";

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

  async function annotateGame(view, slug) {
    const panel = page.panel("romledger");
    for (const disc of view.discs) {
      const result = await lookupDisc(disc, slug);
      panel.append(page.row(disc.name, result.ok ? page.matchBadge(result.match) : page.failure(result)));
    }
  }

  async function annotateList(site, view, slug) {
    if (!slug) {
      page.setStatus(true, `romledger does not track ${view.system || "this system"}.`);
      return;
    }
    const matches = new Map();
    await page.forEachLimited(view.rows, async (row) => {
      const reply = await page.ask({
        type: "lookup-name",
        name: row.title,
        platform: slug,
        regions: row.regions,
      });
      if (reply.ok) {
        matches.set(row, romledger.best(reply.data.matches));
      }
      row.link.after(" ", reply.ok ? page.matchBadge(matches.get(row)) : page.failure(reply));
    });
    await missingQueue.setUp(
      site,
      view.rows
        .filter((row) => matches.has(row))
        .map((row) => ({ title: row.title, url: row.url, match: matches.get(row) })),
    );
  }

  const site = romledger.siteFor(location.hostname);
  const view = site ? site.read(location, document) : null;
  if (!view) {
    return;
  }
  if (view.kind === "unrecognized") {
    page.setStatus(false, view.detail);
    return;
  }
  const platforms = await page.ask({ type: "platforms" });
  if (!platforms.ok) {
    page.failurePanel(platforms);
    return;
  }
  const slug = romledger.slugFor(platforms.data, site.id, view.system);
  if (view.kind === "game") {
    await annotateGame(view, slug);
  } else {
    await annotateList(site, view, slug);
  }
});
