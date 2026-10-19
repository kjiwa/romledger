from dataclasses import dataclass


# What a source offers follows from how its site may be used. A site behind a human check (a
# Turnstile page) can only be used from the browser. A site whose robots.txt and terms allow
# scripts can be fetched from the command line.
@dataclass(frozen=True)
class SourceInfo:
    label: str
    hosts: tuple[str, ...]
    fetch: bool


SOURCES = {
    "vimm": SourceInfo(label="Vimm's Lair", hosts=("vimm.net",), fetch=False),
    "consoleroms": SourceInfo(
        label="ConsoleRoms",
        hosts=("www.consoleroms.com", "downloads.consoleroms.com"),
        fetch=True,
    ),
}
