class FetchError(Exception):
    pass


class SourceChanged(Exception):
    def __init__(self, url: str, what: str) -> None:
        self.url = url
        self.what = what
        super().__init__(
            f"{url}: {what}. The site layout may have changed; "
            "update romledger or report it, and download this game manually."
        )


class SourceBlocked(Exception):
    def __init__(self, url: str, rule: str) -> None:
        super().__init__(f"{url}: not fetched, {rule}")
