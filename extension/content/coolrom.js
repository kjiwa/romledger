page.run(async () => {
  "use strict";

  const GAME_LINK = /^\/roms\/([^/]+)\/\d+\/[^/]+\.php$/;

  async function lookup(name, slug) {
    const reply = await page.ask({ type: "lookup-name", name, platform: slug });
    return reply.ok ? page.matchBadge(romledger.best(reply.data.matches)) : page.failure(reply);
  }

  const system = romledger.coolromSystemFromPath(location.pathname);
  if (!system) {
    return;
  }
  const platforms = await page.ask({ type: "platforms" });
  if (!platforms.ok) {
    page.failurePanel(platforms);
    return;
  }
  const slug = romledger.slugFor(platforms.data, "coolrom", system);
  if (!slug) {
    page.setStatus(true, `romledger does not track ${system}.`);
    return;
  }
  if (GAME_LINK.test(location.pathname)) {
    const name = romledger.coolromNameFromPath(location.pathname);
    page.panel("romledger").append(page.row(name, await lookup(name, slug)));
    return;
  }
  const links = [...document.querySelectorAll("a[href]")].filter(
    (link) => GAME_LINK.test(new URL(link.href).pathname) && link.textContent.trim(),
  );
  if (!links.length) {
    page.setStatus(false, "CoolROM page layout not recognized: no game links found.");
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
