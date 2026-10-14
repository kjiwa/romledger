(async () => {
  "use strict";

  const item = romledger.archiveItemFromPath(location.pathname);
  const reply = await page.ask({ type: "platforms" });
  if (!item) {
    return;
  }
  const panel = page.panel("romledger");
  if (!reply.ok) {
    panel.append(page.failure(reply));
    return;
  }
  const platform = reply.data.find((entry) => entry.sites.archive_item === item);
  if (!platform) {
    panel.append(page.row("This item", page.badge("Not configured", "unknown", "No platform lists this item as archive_item.")));
    return;
  }
  panel.append(page.row(platform.name, page.badge(romledger.progress(platform), "have")));
})();
