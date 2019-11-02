"""A module containing a repository factory."""

import enum

from repository import coolrom, vimms_lair


class RepositoryType(enum.Enum):
    """An enumeration of supported repository types."""
    COOLROM = 'coolrom'
    VIMMS_LAIR = 'vimmslair'


class RepositoryFactory:
    """A factory for the creation of game repository objects."""

    @staticmethod
    def get_repository(
            repository_type, retries=1, retry_delay=0, proxy_type=None, proxy_host=None,
            proxy_port=None, proxy_user=None, proxy_password=None, chunk_size=1024 * 1024):
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

        Raises:
            RuntimeError: The repository type is not supported.
        """
        # pylint: disable=no-else-return
        if repository_type == RepositoryType.COOLROM:
            return coolrom.CoolRomRepository(
                retries, retry_delay, proxy_type, proxy_host, proxy_port, proxy_user,
                proxy_password, chunk_size)
        elif repository_type == RepositoryType.VIMMS_LAIR:
            return vimms_lair.VimmsLairRepository(
                retries, retry_delay, proxy_type, proxy_host, proxy_port, proxy_user,
                proxy_password, chunk_size)

        raise RuntimeError('Unknown repository type {}'.format(repository_type))
