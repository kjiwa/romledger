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
  const STATE_ORDER = ["have", "inbox", "missing", "unwanted", "unscanned", "unknown"];

  function describe(match) {
    const [text, kind] = STATES[match.state] || STATES.unknown;
    const approximate = match.exact === false && match.state !== "unknown";
    return { text: approximate ? `${text} (approximate)` : text, kind, approximate };
  }

  function best(matches, fallback = { state: "unknown" }) {
    if (!matches.length) {
      return fallback;
    }
    const rank = (match) => STATE_ORDER.indexOf(match.state);
    const picked = matches.reduce((leader, match) => (rank(match) < rank(leader) ? match : leader));
    return matches.length > 1 ? { ...picked, exact: false } : picked;
  }

  function regionsOf(row) {
    if (!row) {
      return [];
    }
    return [...row.querySelectorAll("img.flag")].map((flag) => flag.title);
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
    let discs;
    try {
      discs = media.map((entry) => ({
        name: stripExtension(decodeBase64(entry.GoodTitle || "")),
        sha1: String(entry.GoodSha1 || "").toLowerCase(),
        serial: entry.Serial || "",
      }));
    } catch {
      return null;
    }
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
    if (!found) {
      return null;
    }
    let name = found[1];
    try {
      name = decodeURIComponent(name);
    } catch {
      // keep the raw segment
    }
    return name.replaceAll("_", " ");
  }

  function consoleromsSystemFromPath(path) {
    const found = /^\/roms\/([^/]+)/.exec(path);
    return found ? found[1] : null;
  }

  function consoleromsGameSlug(path) {
    const found = /^\/roms\/[^/]+\/([^/]+)$/.exec(path);
    return found && found[1] !== "page" ? found[1] : null;
  }

  const EMULAND_GROUPS = "consoles|portable|computers|arcade";
  const EMULAND_SYSTEM = new RegExp(`^(?:/en)?/(${EMULAND_GROUPS})/([^/]+)`);
  const EMULAND_GAME = new RegExp(`^(?:/en)?/(?:${EMULAND_GROUPS})/[^/]+/(?:roms|games|iso)/([^/]+)$`);
  const EMULAND_INDEX_PAGES = /^(?:[a-z]|0-9|a-z|best|homebrew|misc|top)$/;

  function emulandSystemFromPath(path) {
    const found = EMULAND_SYSTEM.exec(path);
    return found ? `${found[1]}/${found[2]}` : null;
  }

  function emulandGameSlug(path) {
    const found = EMULAND_GAME.exec(path);
    return found && !EMULAND_INDEX_PAGES.test(found[1]) ? found[1] : null;
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

  const DOWNLOAD_FOLDER = "romledger";
  const VIMM_DOWNLOAD_HOST = /^([a-z0-9-]+\.)+vimm\.net$/;

  function hostOf(url) {
    try {
      return new URL(url).hostname.toLowerCase();
    } catch {
      return "";
    }
  }

  function isVimmDownload(item) {
    return [item.finalUrl, item.url].some((url) => VIMM_DOWNLOAD_HOST.test(hostOf(url)));
  }

  function safeFilename(path) {
    const name = String(path || "").split(/[\\/]/).pop();
    return name.replace(/[\u0000-\u001f]/g, "").replace(/^\.+/, "").trim();
  }

  function downloadTarget(item) {
    const name = safeFilename(item.filename);
    return name === "" ? null : `${DOWNLOAD_FOLDER}/${name}`;
  }

  const api = {
    isVimmDownload,
    downloadTarget,
    describe,
    best,
    regionsOf,
    parseAllMedia,
    stripExtension,
    vimmSystemFromTitle,
    coolromSystemFromPath,
    coolromNameFromPath,
    consoleromsSystemFromPath,
    consoleromsGameSlug,
    emulandSystemFromPath,
    emulandGameSlug,
    archiveItemFromPath,
    slugFor,
    progress,
  };
  return api;
})();

if (typeof module !== "undefined") {
  module.exports = romledger;
}
