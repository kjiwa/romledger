// The adapter for Vimm's Lair. A site adapter tells the generic scripts how to read one site:
//   id           the key of the site's codes in the platform list
//   label        the name shown to the person
//   hosts        the host names its pages are served from
//   isDownload   whether a browser download comes from the site
//   read         the page's kind and games, or null when there is nothing to do on it
//   downloadUrl  the address a game page offers for its download, or null
//   messages     the site's own wording for a slow-down answer and a missing download
(() => {
  "use strict";

  const HASH_LENGTH = 40;
  const GAME_PATH = /^\/vault\/\d+\/?$/;
  const SECTION_PATH = /^\/vault\/([^/\d][^/]*)\/(?:[A-Za-z]|number)\/?$/;
  const DOWNLOAD_HOST = /^([a-z0-9-]+\.)+vimm\.net$/;

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

  function systemFromTitle(title) {
    const found = /\(([^()]+)\)\s*$/.exec(title.trim());
    return found ? found[1] : null;
  }

  function safeDecode(text) {
    try {
      return decodeURIComponent(text);
    } catch {
      return text;
    }
  }

  function listSystem(url) {
    let parsed;
    try {
      parsed = new URL(url);
    } catch {
      return null;
    }
    if (parsed.searchParams.get("p") === "list") {
      return parsed.searchParams.get("system") || null;
    }
    const section = SECTION_PATH.exec(parsed.pathname);
    return section ? safeDecode(section[1]) : null;
  }

  function regionsOf(row) {
    if (!row) {
      return [];
    }
    return [...row.querySelectorAll("img.flag")].map((flag) => flag.title);
  }

  function hostOf(url) {
    try {
      return new URL(url).hostname.toLowerCase();
    } catch {
      return "";
    }
  }

  function isDownload(item) {
    return [item.finalUrl, item.url].some((url) => DOWNLOAD_HOST.test(hostOf(url)));
  }

  function downloadUrl(doc, pageUrl) {
    const form = doc.querySelector("#dl-form");
    if (!form) {
      return null;
    }
    let target;
    try {
      target = new URL(form.getAttribute("action") || "", pageUrl);
    } catch {
      return null;
    }
    target.protocol = "https:";
    target.search = "";
    const fields = [...form.querySelectorAll("input[name], select[name]")].filter(
      (field) => !field.disabled,
    );
    for (const field of fields) {
      const value = field.tagName === "SELECT" ? field.value : field.getAttribute("value");
      target.searchParams.append(field.getAttribute("name"), value || "");
    }
    const complete = target.searchParams.has("mediaId") && target.searchParams.has("token");
    return complete && isDownload({ url: target.href }) ? target.href : null;
  }

  function readGame(doc) {
    const source = [...doc.scripts]
      .map((script) => script.textContent)
      .find((text) => text.includes("allMedia"));
    const discs = parseAllMedia(source || "");
    if (!discs) {
      return {
        kind: "unrecognized",
        detail: "Vimm's Lair page layout not recognized: the allMedia data is missing.",
      };
    }
    return { kind: "game", system: systemFromTitle(doc.title), discs };
  }

  function readList(doc, system) {
    const links = [...doc.querySelectorAll("td a[href]")].filter((link) =>
      GAME_PATH.test(new URL(link.href).pathname),
    );
    if (!links.length) {
      return {
        kind: "unrecognized",
        detail: "Vimm's Lair page layout not recognized: no game links found.",
      };
    }
    const rows = links.map((link) => ({
      title: link.textContent.trim(),
      url: link.href,
      regions: regionsOf(link.closest("tr")),
      link,
    }));
    return { kind: "list", system, rows };
  }

  function read(location, doc) {
    if (GAME_PATH.test(location.pathname)) {
      return readGame(doc);
    }
    const system = listSystem(location.href);
    return system ? readList(doc, system) : null;
  }

  const site = {
    id: "vimm",
    label: "Vimm's Lair",
    hosts: ["vimm.net"],
    isDownload,
    read,
    downloadUrl,
    messages: {
      slowDown: "Vimm's Lair says to slow down. Try again later.",
      paused:
        "Vimm's Lair did not offer a download. Open a game page, pass the check, then press Resume.",
    },
    parseAllMedia,
    listSystem,
    systemFromTitle,
    regionsOf,
  };

  if (typeof romledger !== "undefined") {
    romledger.register(site);
  }
  if (typeof module !== "undefined") {
    module.exports = site;
  }
})();
