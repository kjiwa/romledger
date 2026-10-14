page.run(async () => {
  "use strict";

  const GAME_PATH = /^\/vault\/\d+\/?$/;

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

  async function annotateList() {
    const system = new URLSearchParams(location.search).get("system");
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
    await page.forEachLimited(links, async (link) => {
      const reply = await page.ask({
        type: "lookup-name",
        name: link.textContent.trim(),
        platform: slug,
        regions: romledger.regionsOf(link.closest("tr")),
      });
      const node = reply.ok ? page.matchBadge(romledger.best(reply.data.matches)) : page.failure(reply);
      link.after(" ", node);
    });
  }

  if (GAME_PATH.test(location.pathname)) {
    await annotateGame();
  } else if (new URLSearchParams(location.search).get("p") === "list") {
    await annotateList();
  }
});
