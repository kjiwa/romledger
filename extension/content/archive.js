page.run(async () => {
  "use strict";

  const item = romledger.archiveItemFromPath(location.pathname);
  if (!item) {
    return;
  }
  const reply = await page.ask({ type: "platforms" });
  if (!reply.ok) {
    page.setStatus(false, reply.error);
    return;
  }
  const platform = reply.data.find((entry) => entry.sites.archive_item === item);
  if (!platform) {
    page.setStatus(true, "This item is not any platform's archive_item.");
    return;
  }
  page.panel("romledger").append(page.row(platform.name, page.badge(romledger.progress(platform), "have")));
});
