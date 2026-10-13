import httpx

from rom_scraper import __version__

USER_AGENT = f"rom-scraper/{__version__} (+https://github.com/kjiwa/rom-scraper)"


def client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=60.0,
        follow_redirects=True,
        trust_env=True,
    )
