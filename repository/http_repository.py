"""A module containing a base class for HTTP repositories."""

import os.path

import requests

from repository import model


class HttpRepository(model.Repository):
    """A class for interacting with HTTP repositories."""

    def __init__(self, headers, proxy_type, proxy_host, proxy_port, proxy_user, proxy_password):
        """Creates a new HTTP repository instance.

        Args:
            headers: Headers to be used for HTTP requests.
            proxy_type: The proxy server type (http, https, or socks5).
            proxy_host: The proxy server host.
            proxy_port: The proxy server port.
            proxy_user: The proxy server user.
            proxy_password: The proxy server password.
        """
        self._headers = headers
        self._proxies = HttpRepository._create_proxies(
            proxy_type, proxy_host, proxy_port, proxy_user, proxy_password)

    @staticmethod
    def _create_proxies(proxy_type, proxy_host, proxy_port, proxy_user, proxy_password):
        if not proxy_type:
            return {}

        credentials = '{}:{}@'.format(proxy_user, proxy_password) if proxy_user else ''
        url = '{}://{}{}:{}'.format(proxy_type, credentials, proxy_host, proxy_port)
        if proxy_type == 'socks5':
            return {
                'http': url,
                'https': url
            }

        return {proxy_type: url}

    def download(self, game):
        for gamefile in game.files:
            # Skip the file if it already exists and has the same size as the remote file.
            dirname = os.path.dirname(game.platform + '/')
            path = '{}/{}'.format(dirname, gamefile.filename)
            while not (os.path.exists(path) and os.path.getsize(path) == gamefile.size_bytes):
                response = requests.get(gamefile.url, headers=self._headers, proxies=self._proxies)
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
