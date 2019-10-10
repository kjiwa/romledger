"""A module containing common repository objects and definitions."""

import dataclasses
import os
import os.path
import typing

import requests


class GameDownloadException(Exception):
    """A class for surfacing game download errors."""


@dataclasses.dataclass(frozen=True)
class Game:
    """A class representing a game entry in a repository."""
    game_id: str
    platform: str
    name: str
    size_bytes: int
    tags: typing.List[str]
    urls: typing.List[str]


class Repository:
    """A base class for game repositories."""

    @staticmethod
    def platforms():
        """Returns the list of supported platforms for this repository."""
        raise NotImplementedError()

    @staticmethod
    def games(platform, section):
        """Returns a list of games a section of the repository.

        Args:
            platform: The game platform.
            section: The repository section to scan.

        Returns:
            A list of games in a section of the repository.
        """
        raise NotImplementedError()

    @staticmethod
    def download(game, headers=None):
        """Downloads a game from the repository and saves it to local storage.

        Args:
            game: The game to download.
            headers: Optional headers to use for the download request.

        Raises:
            GameDownloadException: The file could not be downloaded.
        """
        for url in game.urls:
            response = requests.get(url, headers=headers, stream=True)
            if response.status_code != 200:
                raise GameDownloadException('Unable to download game {}: {}'.format(game.name, response.content))

            # Create the platform directory.
            dirname = os.path.dirname(game.platform + '/')
            if not os.path.exists(dirname):
                os.makedirs(dirname)

            # Skip the file if it already exists.
            filename = Repository._get_filename(response, game)
            path = '{}/{}'.format(dirname, filename)
            if os.path.exists(path):
                return

            # Write the file.
            with open(path, 'wb') as gamefile:
                gamefile.write(response.content)

            response.close()

    @staticmethod
    def _get_filename(response, game):
        # Get file name from the Content-Disposition header.
        content_disposition = response.headers.get('Content-Disposition', '')
        if not content_disposition:
            raise GameDownloadException(
                'Unable to determine file name for game {} ({})'.format(game.name, game.platform))

        filenames = [i.split('=')[1][1:-1] for i in content_disposition.split(';') if i.strip().startswith('filename=')]
        if not filenames:
            raise GameDownloadException(
                'Unable to determine file name for game {} ({})'.format(game.name, game.platform))

        return filenames[0]
