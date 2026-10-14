page.run(async () => {
  "use strict";

  async function lookup(name, slug) {
    const reply = await page.ask({ type: "lookup-name", name, platform: slug });
    return reply.ok ? page.matchBadge(romledger.best(reply.data.matches)) : page.failure(reply);
  }

  const system = romledger.emulandSystemFromPath(location.pathname);
  if (!system) {
    return;
  }
  const platforms = await page.ask({ type: "platforms" });
  if (!platforms.ok) {
    page.failurePanel(platforms);
    return;
  }
  const slug = romledger.slugFor(platforms.data, "emuland", system);
  if (!slug) {
    page.setStatus(true, `romledger does not track ${system}.`);
    return;
  }
  if (romledger.emulandGameSlug(location.pathname)) {
    const title = document.querySelector("h1");
    const name = title && title.textContent.replace(/\s+/g, " ").trim();
    if (!name) {
      page.setStatus(false, "emu-land page layout not recognized: no game title found.");
      return;
    }
    page.panel("romledger").append(page.row(name, await lookup(name, slug)));
    return;
  }
  const links = [...document.querySelectorAll("a[href]")].filter(
    (link) =>
      romledger.emulandGameSlug(new URL(link.href).pathname) &&
      !link.classList.contains("btn") &&
      link.textContent.trim(),
  );
  if (!links.length) {
    page.setStatus(false, "emu-land page layout not recognized: no game links found.");
    return;
  }
  const seen = new Set();
  await page.forEachLimited(links, async (link) => {
    const key = link.getAttribute("href");
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    link.after(" ", await lookup(link.textContent.replace(/\s+/g, " ").trim(), slug));
  });
});
