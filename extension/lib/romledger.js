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
  const STATE_ORDER = ["have", "inbox", "missing", "unwanted", "unscanned", "unknown"];
  const DOWNLOAD_FOLDER = "romledger";
  const DEFAULT_GAP_SECONDS = 15;
  const MIN_GAP_SECONDS = 15;
  const MAX_GAP_SECONDS = 600;
  const sites = {};

  // A site adapter (see sites/vimm.js) registers itself here, and the generic scripts find it by
  // the page's host.
  function register(site) {
    sites[site.id] = site;
  }

  function siteFor(hostname) {
    return Object.values(sites).find((site) => site.hosts.includes(hostname)) || null;
  }

  function isSiteDownload(item) {
    return Object.values(sites).some((site) => site.isDownload(item));
  }

  function gapSeconds(stored) {
    const seconds = Number(stored);
    if (stored === undefined || stored === null || stored === "" || !Number.isFinite(seconds)) {
      return DEFAULT_GAP_SECONDS;
    }
    return Math.min(MAX_GAP_SECONDS, Math.max(MIN_GAP_SECONDS, seconds));
  }

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

  function safeFilename(path) {
    const name = String(path || "").split(/[\\/]/).pop();
    return name.replace(/[\u0000-\u001f]/g, "").replace(/^\.+/, "").trim();
  }

  function downloadTarget(item) {
    const name = safeFilename(item.filename);
    return name === "" ? null : `${DOWNLOAD_FOLDER}/${name}`;
  }

  function queueable(entries) {
    const ready = entries.filter((entry) => entry.match.state === "missing");
    const approximate = ready.filter((entry) => describe(entry.match).approximate).length;
    return { ready, approximate };
  }

  return {
    register,
    siteFor,
    sites,
    isSiteDownload,
    gapSeconds,
    describe,
    best,
    slugFor,
    progress,
    downloadTarget,
    queueable,
    MIN_GAP_SECONDS,
    MAX_GAP_SECONDS,
  };
})();

if (typeof module !== "undefined") {
  module.exports = romledger;
}
