page.run(async () => {
  "use strict";

  async function lookup(name, slug) {
    const reply = await page.ask({ type: "lookup-name", name, platform: slug });
    return reply.ok ? page.matchBadge(romledger.best(reply.data.matches)) : page.failure(reply);
  }

  const system = romledger.consoleromsSystemFromPath(location.pathname);
  if (!system) {
    return;
  }
  const platforms = await page.ask({ type: "platforms" });
  if (!platforms.ok) {
    page.failurePanel(platforms);
    return;
  }
  const slug = romledger.slugFor(platforms.data, "consoleroms", system);
  if (!slug) {
    page.setStatus(true, `romledger does not track ${system}.`);
    return;
  }
  if (romledger.consoleromsGameSlug(location.pathname)) {
    const title = document.querySelector('h1[itemprop="name"]');
    if (!title || !title.textContent.trim()) {
      page.setStatus(false, "ConsoleRoms page layout not recognized: no game title found.");
      return;
    }
    const name = title.textContent.trim();
    page.panel("romledger").append(page.row(name, await lookup(name, slug)));
    return;
  }
  const links = [...document.querySelectorAll("a[href]")].filter(
    (link) =>
      romledger.consoleromsGameSlug(new URL(link.href).pathname) &&
      link.getAttribute("role") !== "button" &&
      link.textContent.trim(),
  );
  if (!links.length) {
    page.setStatus(false, "ConsoleRoms page layout not recognized: no game links found.");
    return;
  }
  const seen = new Set();
  await page.forEachLimited(links, async (link) => {
    const key = link.getAttribute("href");
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    link.after(" ", await lookup(link.textContent.trim(), slug));
  });
});
