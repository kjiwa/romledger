import httpx
import pytest

from conftest import FakeThrottle
from romledger import __version__, http
from romledger.sources.errors import SourceBlocked


def test_client_settings() -> None:
    with http.client() as client:
        assert client.headers["User-Agent"] == (
            f"romledger/{__version__} (+https://github.com/kjiwa/romledger)"
        )
        assert client.timeout.read == 60.0
        assert client.follow_redirects


def test_client_without_proxy_does_not_prompt() -> None:
    def prompt(_: str) -> str:
        raise AssertionError("prompted")

    with http.client(prompt=prompt, interactive=lambda: True):
        pass


@pytest.mark.parametrize("scheme", http.PROXY_SCHEMES)
def test_client_accepts_proxy_schemes(scheme: str) -> None:
    with http.client(f"{scheme}://proxy.example:1080"):
        pass


def test_client_prompts_for_missing_password() -> None:
    asked: list[str] = []

    def prompt(message: str) -> str:
        asked.append(message)
        return "pw"

    with http.client("http://alice@proxy.example:3128", prompt, lambda: True):
        pass
    assert asked == ["Proxy password for alice@proxy.example:3128: "]
    assert "pw" not in asked[0]


def never(_: str) -> str:
    raise AssertionError("prompted")


@pytest.mark.parametrize(
    ("url", "interactive"),
    [
        ("http://proxy.example:3128", True),
        ("http://alice:secret@proxy.example:3128", True),
        ("http://alice:@proxy.example:3128", True),
        ("http://alice@proxy.example:3128", False),
    ],
)
def test_with_password_leaves_url_alone(url: str, interactive: bool) -> None:
    assert http.with_password(url, never, lambda: interactive) == url


def test_with_password_quotes_the_password() -> None:
    result = http.with_password(
        "socks5://alice@proxy.example:1080", lambda _: "p@ss/w:d", lambda: True
    )
    assert result == "socks5://alice:p%40ss%2Fw%3Ad@proxy.example:1080"


def test_stdin_is_tty_under_pytest() -> None:
    assert http.stdin_is_tty() in (True, False)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://alice:secret@proxy.example:3128", "http://***@proxy.example:3128"),
        ("socks5://alice@proxy.example:1080", "socks5://***@proxy.example:1080"),
        ("http://proxy.example:3128", "http://proxy.example:3128"),
    ],
)
def test_redact(url: str, expected: str) -> None:
    assert http.redact(url) == expected


def test_throttle_spaces_requests_per_host(fake_throttle: FakeThrottle) -> None:
    throttle, sleeps = fake_throttle(2.0)
    throttle.wait("https://a.example/1")
    throttle.wait("https://b.example/1")
    throttle.wait("https://a.example/2")
    assert sleeps == [2.0]


def test_throttle_does_not_sleep_after_the_gap(fake_throttle: FakeThrottle) -> None:
    throttle, sleeps = fake_throttle(0.0)
    throttle.wait("https://a.example/1")
    throttle.wait("https://a.example/2")
    assert sleeps == []


def test_throttle_per_host_gap(fake_throttle: FakeThrottle) -> None:
    throttle, sleeps = fake_throttle(1.0)
    throttle.set_gap("a.example", 10.0)
    throttle.wait("https://a.example/1")
    throttle.wait("https://a.example/2")
    assert sleeps == [10.0]


def robots_client(status: int, body: str, requests: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(status, text=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def load(status: int, body: str) -> http.Robots:
    return http.load_robots(
        "https://a.example", robots_client(status, body, []), http.Throttle(0.0)
    )


def test_robots_rules_and_crawl_delay() -> None:
    robots = load(200, "User-agent: *\nCrawl-delay: 10\nDisallow: /admin/\n")
    assert robots.crawl_delay == 10.0
    assert robots.allowed("https://a.example/roms/")
    assert not robots.allowed("https://a.example/admin/x")


def test_robots_without_crawl_delay() -> None:
    assert load(200, "User-agent: *\nDisallow:\n").crawl_delay == 0.0


@pytest.mark.parametrize("status", [404, 410])
def test_robots_missing_allows_everything(status: int) -> None:
    assert load(status, "").allowed("https://a.example/anything")


@pytest.mark.parametrize("status", [401, 403, 500])
def test_robots_error_blocks_everything(status: int) -> None:
    assert not load(status, "").allowed("https://a.example/anything")


def test_require_allowed_names_url_and_robots() -> None:
    robots = load(200, "User-agent: *\nDisallow: /admin/\n")
    http.require_allowed(robots, "https://a.example/ok")
    with pytest.raises(SourceBlocked) as error:
        http.require_allowed(robots, "https://a.example/admin/x")
    assert "https://a.example/admin/x" in str(error.value)
    assert "a.example/robots.txt" in str(error.value)
