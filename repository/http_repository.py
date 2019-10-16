"""A module containing a base class for HTTP repositories."""

import os.path

import requests

from repository import model


class HttpRepository(model.Repository):
    """A class for interacting with HTTP repositories."""

    def __init__(self, headers):
        self._headers = headers

    def download(self, game):
        for gamefile in game.files:
            # Skip the file if it already exists and has the same size as the remote file.
            dirname = os.path.dirname(game.platform + '/')
            path = '{}/{}'.format(dirname, gamefile.filename)
            while not (os.path.exists(path) and os.path.getsize(path) == gamefile.size_bytes):
                response = requests.get(gamefile.url, headers=self._headers)
                if response.status_code != 200:
                    raise model.GameDownloadException(
                        'Unable to download game {}: {}'.format(game.name, response.content))

                # Create the platform directory.
                if not os.path.exists(dirname):
                    os.makedirs(dirname)

                # Write the file.
                with open(path, 'wb') as f:
                    f.write(response.content)

                response.close()
