from dataclasses import dataclass

HASH = "hash"
TITLE = "title"


# What a source offers follows from how its site may be used. A site behind a human check (a
# Turnstile page) can only be used from the browser. A site whose robots.txt and terms allow
# scripts can be fetched from the command line. A source matches by hash only where the site
# publishes hashes.
@dataclass(frozen=True)
class SourceInfo:
    name: str
    label: str
    hosts: tuple[str, ...]
    fetch: bool
    browser: bool
    match: str


SOURCES = {
    "vimm": SourceInfo(
        name="vimm",
        label="Vimm's Lair",
        hosts=("vimm.net",),
        fetch=False,
        browser=True,
        match=HASH,
    ),
    "consoleroms": SourceInfo(
        name="consoleroms",
        label="ConsoleRoms",
        hosts=("www.consoleroms.com", "downloads.consoleroms.com"),
        fetch=True,
        browser=False,
        match=TITLE,
    ),
}
