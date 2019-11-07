"""A module containing common repository objects and definitions."""

import dataclasses
import os.path
import typing


class GameDownloadException(Exception):
    """A class for surfacing game download errors."""


class GameScrapeException(Exception):
    """A class for surfacing game scraping errors."""


@dataclasses.dataclass(frozen=True)
class GameFile:
    """A class representing a game file."""
    filename: str
    size_bytes: int
    url: str

    def __eq__(self, other):
        # Ignore file extensions when comparing filenames. This is because sometimes file
        # extensions vary between download mirrors. For example, one download server may serve
        # game.zip while the other may serve game.7z. Considering these filenames equal prevents
        # duplicate downloads.
        return os.path.splitext(self.filename)[0] == os.path.splitext(other.filename)[0]


@dataclasses.dataclass(frozen=True)
class Game:
    """A class representing a game entry in a repository."""
    game_id: str
    platform: str
    name: str
    tags: typing.List[str]
    files: typing.Set[GameFile]


class Repository:
    """A base class for game repositories."""

    def platforms(self):
        """Returns the list of supported platforms for this repository."""
        raise NotImplementedError()

    def games(self, platform, section):
        """Returns a list of games a section of the repository.

        Args:
            platform: The game platform.
            section: The repository section to scan.

        Returns:
            A list of games in a section of the repository.
        """
        raise NotImplementedError()

    def download(self, game):
        """Downloads a game from the repository and saves it to local storage.

        Args:
            game: The game to download.

        Raises:
            GameDownloadException: The file could not be downloaded.
        """
        raise NotImplementedError()
