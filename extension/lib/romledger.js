const romledger = (() => {
  "use strict";

  const STATES = {
    have: ["In library", "have"],
    inbox: ["In inbox", "inbox"],
    missing: ["Missing", "missing"],
    unwanted: ["Not wanted", "unwanted"],
    unscanned: ["Not scanned", "unknown"],
    unknown: ["Not in any DAT", "unknown"],
  };
  const HASH_LENGTH = 40;

  function describe(match) {
    const [text, kind] = STATES[match.state] || STATES.unknown;
    const approximate = match.exact === false && match.state !== "unknown";
    return { text: approximate ? `${text} (approximate)` : text, kind, approximate };
  }

  function decodeBase64(text) {
    const binary = atob(text);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  }

  function stripExtension(name) {
    return name.replace(/\.[A-Za-z0-9]{1,5}$/, "");
  }

  function parseAllMedia(source) {
    const found = /allMedia\s*=\s*(\[.*?\]);/s.exec(source);
    if (!found) {
      return null;
    }
    let media;
    try {
      media = JSON.parse(found[1]);
    } catch {
      return null;
    }
    const discs = media.map((entry) => ({
      name: stripExtension(decodeBase64(entry.GoodTitle || "")),
      sha1: String(entry.GoodSha1 || "").toLowerCase(),
      serial: entry.Serial || "",
    }));
    return discs.every((disc) => disc.sha1.length === HASH_LENGTH && disc.name) ? discs : null;
  }

  function vimmSystemFromTitle(title) {
    const found = /\(([^()]+)\)\s*$/.exec(title.trim());
    return found ? found[1] : null;
  }

  function coolromSystemFromPath(path) {
    const found = /^\/roms\/([^/]+)\//.exec(path);
    return found ? found[1] : null;
  }

  function coolromNameFromPath(path) {
    const found = /\/([^/]+)\.php$/.exec(path);
    return found ? decodeURIComponent(found[1]).replaceAll("_", " ") : null;
  }

  function archiveItemFromPath(path) {
    const found = /^\/details\/([^/?#]+)/.exec(path);
    return found ? decodeURIComponent(found[1]) : null;
  }

  function slugFor(platforms, site, code) {
    const wanted = String(code || "").toLowerCase();
    const found = platforms.find((platform) => {
      const value = platform.sites && platform.sites[site];
      return wanted !== "" && typeof value === "string" && value.toLowerCase() === wanted;
    });
    return found ? found.slug : null;
  }

  function progress(platform) {
    if (platform.percent === null || platform.percent === undefined) {
      return "Not scanned";
    }
    return `${platform.have} of ${platform.wanted} wanted games (${platform.percent}%)`;
  }

  const api = {
    describe,
    parseAllMedia,
    stripExtension,
    vimmSystemFromTitle,
    coolromSystemFromPath,
    coolromNameFromPath,
    archiveItemFromPath,
    slugFor,
    progress,
  };
  return api;
})();

if (typeof module !== "undefined") {
  module.exports = romledger;
}
