import getpass
import sys
import time
from collections.abc import Callable
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from romledger import __version__
from romledger.sources.errors import SourceBlocked

USER_AGENT = f"romledger/{__version__} (+https://github.com/kjiwa/romledger)"
ROBOTS_AGENT = "romledger"
PROXY_SCHEMES = ("http", "https", "socks5", "socks5h")
DEFAULT_GAP = 1.0

Prompt = Callable[[str], str]
Interactive = Callable[[], bool]


def redact(url: str) -> str:
    parts = urlsplit(url)
    userinfo, at, hostport = parts.netloc.rpartition("@")
    return url if not at or not userinfo else urlunsplit(parts._replace(netloc=f"***@{hostport}"))


def stdin_is_tty() -> bool:
    return sys.stdin.isatty()


def with_password(
    url: str, prompt: Prompt = getpass.getpass, interactive: Interactive = stdin_is_tty
) -> str:
    parts = urlsplit(url)
    userinfo, at, hostport = parts.netloc.rpartition("@")
    user, colon, _ = userinfo.partition(":")
    if not at or not user or colon or not interactive():
        return url
    password = prompt(f"Proxy password for {user}@{hostport}: ")
    return urlunsplit(parts._replace(netloc=f"{user}:{quote(password, safe='')}@{hostport}"))


def client(
    proxy: str | None = None,
    prompt: Prompt = getpass.getpass,
    interactive: Interactive = stdin_is_tty,
) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=60.0,
        follow_redirects=True,
        trust_env=True,
        proxy=with_password(proxy, prompt, interactive) if proxy else None,
    )


class Throttle:
    def __init__(
        self,
        gap: float = DEFAULT_GAP,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._gap = gap
        self._clock = clock
        self._sleep = sleep
        self._gaps: dict[str, float] = {}
        self._last: dict[str, float] = {}

    def set_gap(self, host: str, seconds: float) -> None:
        self._gaps[host] = seconds

    def wait(self, url: str) -> None:
        host = urlsplit(url).hostname or ""
        last = self._last.get(host)
        if last is not None:
            remaining = last + self._gaps.get(host, self._gap) - self._clock()
            if remaining > 0:
                self._sleep(remaining)
        self._last[host] = self._clock()


class Robots:
    def __init__(self, parser: RobotFileParser) -> None:
        self._parser = parser
        delay = parser.crawl_delay(ROBOTS_AGENT)
        self.crawl_delay = float(delay) if delay is not None else 0.0

    def allowed(self, url: str) -> bool:
        return self._parser.can_fetch(ROBOTS_AGENT, url)


def load_robots(base_url: str, client: httpx.Client, throttle: Throttle) -> Robots:
    robots_url = f"{base_url}/robots.txt"
    throttle.wait(robots_url)
    response = client.get(robots_url)
    parser = RobotFileParser()
    parser.parse(_robots_lines(response))
    return Robots(parser)


def _robots_lines(response: httpx.Response) -> list[str]:
    if response.status_code == httpx.codes.OK:
        return response.text.splitlines()
    missing = response.status_code in (httpx.codes.NOT_FOUND, httpx.codes.GONE)
    return ["User-agent: *", "Allow: /" if missing else "Disallow: /"]


def require_allowed(robots: Robots, url: str) -> None:
    if not robots.allowed(url):
        host = urlsplit(url).netloc
        raise SourceBlocked(url, f"{host}/robots.txt disallows it for user agent {ROBOTS_AGENT}")
