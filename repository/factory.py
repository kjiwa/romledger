"""A module containing a repository factory."""

import enum

from repository import coolrom, vimms_lair

DEFAULT_HTTP_RETRIES = 1
DEFAULT_HTTP_RETRY_DELAY_SECONDS = 0
DEFAULT_HTTP_CHUNK_SIZE_BYTES = 1024 * 1024  # 1 MiB
DEFAULT_HTTP_TIMEOUT_SECONDS = 60


class RepositoryType(enum.Enum):
    """An enumeration of supported repository types."""
    COOLROM = 'coolrom'
    VIMMS_LAIR = 'vimmslair'


class RepositoryFactory:
    """A factory for the creation of game repository objects."""

    @staticmethod
    def get_repository(
            repository_type, retries=DEFAULT_HTTP_RETRIES,
            retry_delay=DEFAULT_HTTP_RETRY_DELAY_SECONDS, proxy_type=None, proxy_host=None,
            proxy_port=None, proxy_user=None, proxy_password=None,
            chunk_size=DEFAULT_HTTP_CHUNK_SIZE_BYTES, timeout=DEFAULT_HTTP_TIMEOUT_SECONDS):
        """Creates a repository instance.

        Args:
            repository_type: The type of repository to create.
            retries: The number of times to retry HTTP requests.
            retry_delay: The number of seconds to wait between retries.
            proxy_type: The proxy server type (http, https, or socks5).
            proxy_host: The proxy server host.
            proxy_port: The proxy server port.
            proxy_user: The proxy server user.
            proxy_password: The proxy server password.
            chunk_size: The chunk size in bytes to use for large downloads.
            timeout: The number of seconds to wait for data from HTTP requests.

        Raises:
            RuntimeError: The repository type is not supported.
        """
        # pylint: disable=no-else-return
        if repository_type == RepositoryType.COOLROM:
            return coolrom.CoolRomRepository(
                retries, retry_delay, proxy_type, proxy_host, proxy_port, proxy_user,
                proxy_password, chunk_size, timeout)
        elif repository_type == RepositoryType.VIMMS_LAIR:
            return vimms_lair.VimmsLairRepository(
                retries, retry_delay, proxy_type, proxy_host, proxy_port, proxy_user,
                proxy_password, chunk_size, timeout)

        raise RuntimeError('Unknown repository type {}'.format(repository_type))
