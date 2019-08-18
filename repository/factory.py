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
    def get_repository(repository_type):
        """Creates a repository instance.

        Args:
            repository_type: The type of repository to create.

        Raises:
            RuntimeError: The repository type is not supported.
        """
        # pylint: disable=no-else-return
        if repository_type == RepositoryType.COOLROM:
            return coolrom.CoolRomRepository()
        elif repository_type == RepositoryType.VIMMS_LAIR:
            return vimms_lair.VimmsLairRepository()

        raise RuntimeError('Unknown repository type %s' % repository_type)
