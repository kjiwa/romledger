import httpx

from romledger import __version__

USER_AGENT = f"romledger/{__version__} (+https://github.com/kjiwa/romledger)"


def client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=60.0,
        follow_redirects=True,
        trust_env=True,
    )
