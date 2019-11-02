"""A module containing a base class for HTTP repositories."""

import functools
import os.path
import time

import requests

from repository import model


class HttpRepository(model.Repository):
    """A class for interacting with HTTP repositories."""

    def __init__(
            self, headers, retries, retry_delay, proxy_type, proxy_host, proxy_port, proxy_user,
            proxy_password, chunk_size):
        """Creates a new HTTP repository instance.

        Args:
            headers: Headers to be used for HTTP requests.
            retries: The number of times to retry HTTP requests.
            retry_delay: The number of seconds to wait between retries.
            proxy_type: The proxy server type (http, https, or socks5).
            proxy_host: The proxy server host.
            proxy_port: The proxy server port.
            proxy_user: The proxy server user.
            proxy_password: The proxy server password.
            chunk_size: The chunk size in bytes to use for large downloads.
        """
        self._headers = headers
        self._retries = retries
        self._retry_delay = retry_delay
        self._proxies = HttpRepository._create_proxies(
            proxy_type, proxy_host, proxy_port, proxy_user, proxy_password)
        self._chunk_size = chunk_size

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
            # Skip the file if it already exists and has the same size as the remote file. Only the
            # existence criteria is used if the game does not specify a file size.
            dirname = os.path.dirname(game.platform + '/')
            path = '{}/{}'.format(dirname, gamefile.filename)
            while not (
                    os.path.exists(path)
                    and (not gamefile.size_bytes or os.path.getsize(path) == gamefile.size_bytes)):
                response = self.retry_get_request(gamefile.url, stream=True)
                if response.status_code != 200:
                    raise model.GameDownloadException(
                        'Unable to download game {}: {}'.format(game.name, response.content))

                # Create the platform directory.
                if not os.path.exists(dirname):
                    os.makedirs(dirname)

                # Write and validate the file.
                with open(path, 'wb') as f:
                    # Download the file in chunks to improve memory usage.
                    for chunk in response.iter_content(chunk_size=self._chunk_size):
                        if chunk:
                            f.write(chunk)

                response.close()

    def retry_get_request(self, url, stream=False, additional_headers=None):
        headers = self._headers
        if additional_headers:
            headers.update(additional_headers)

        return self._retry_request(functools.partial(
            requests.get, url, headers=headers, proxies=self._proxies, stream=stream))

    def retry_head_request(self, url):
        return self._retry_request(functools.partial(
            requests.head, url, headers=self._headers, proxies=self._proxies))

    def _retry_request(self, request):
        response = None
        for i in range(0, self._retries):
            response = request()
            if response.status_code == 200:
                break

            # Implement exponential backoff between download attempts.
            time.sleep((2 ** i) * self._retry_delay)

        return response
