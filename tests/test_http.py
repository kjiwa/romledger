from rom_scraper import __version__, http


def test_client_settings() -> None:
    with http.client() as client:
        assert client.headers["User-Agent"] == (
            f"rom-scraper/{__version__} (+https://github.com/kjiwa/rom-scraper)"
        )
        assert client.timeout.read == 60.0
        assert client.follow_redirects
