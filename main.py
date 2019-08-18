""""A program that downloads games from repositories such as Vimm's Lair and CoolROM."""

import argparse
import logging
import string
import time

import repository

SCRAPER_TIME_FORMAT = '%H:%M:%S'


def get_logger(log_level):
    """Initializes and returns a logger instance.

    Args:
        log_level: The logging level.

    Returns:
        A logger instance.
    """
    logging.basicConfig()
    logger = logging.getLogger()

    if log_level == 'notset':
        logger.setLevel(logging.NOTSET)
    elif log_level == 'debug':
        logger.setLevel(logging.DEBUG)
    elif log_level == 'info':
        logger.setLevel(logging.INFO)
    elif log_level == 'warning':
        logger.setLevel(logging.WARNING)
    elif log_level == 'error':
        logger.setLevel(logging.ERROR)
    elif log_level == 'critical':
        logger.setLevel(logging.CRITICAL)

    return logger


def is_download_allowed(game, allowed_tags):
    """Checks if a game is allowed to be downloaded.

    Args:
        game: The game to be checked.
        allowed_tags: A list of tags that may be downloaded.

    Returns:
        True if all of the game's tags are allowed; false otherwise.
    """
    for tag in game.tags:
        if tag not in allowed_tags:
            return False

    return True


def retry_download(repo, game, retries):
    """Tries to download a game a specified number of times before failing.

    Args:
        repo: The repository from which to download the game.
        game: The game to be downloaded.
        retries: The number of times to try to download the game.

    Raises:
        GameDownloadException: The game could not be downloaded.
    """
    for i in range(0, retries):
        try:
            repo.download(game)
            return
        except repository.GameDownloadException as ex:
            if i == retries - 1:
                raise ex


def get_download_duration(download_start):
    """Computes the duration of a download and returns it in a displayable format.

    Args:
        download_start: The time at which the download began.

    Returns:
        A string showing the duration of the download.
    """
    return time.strftime(SCRAPER_TIME_FORMAT, time.gmtime(time.time() - download_start))


def parse_arguments():
    """Parses command line arguments.

    Returns:
        An object containing program options.
    """
    parser = argparse.ArgumentParser()

    # Repository arguments.
    repo_group = parser.add_argument_group('repository')
    repo_group.add_argument('--repository', required=True, choices=[i.value for i in repository.RepositoryType],
                            help='The repository to scan for games.')
    repo_group.add_argument('--platform', required=True, help='The platform for which to download games.')
    repo_group.add_argument('--section', action='append', choices=['#'] + list(string.ascii_lowercase),
                            help='The sections to scan for games.')
    repo_group.add_argument('--pretend', action='store_true', help='Whether to pretend downloading games.')
    repo_group.add_argument('--retries', default=3, type=int, help='The number of times to try to download a game.')
    repo_group.add_argument('--allow_tag', action='append', help='Allow games with a tag to be downloaded.')

    # Logging arguments.
    logging_group = repo_group.add_argument_group('logging')
    logging_group.add_argument('--log_level', default='info',
                               choices=['notset', 'debug', 'info', 'warning', 'error', 'critical'])

    return parser.parse_args()


def main():
    """Parses program options and initiates game downloads."""
    args = parse_arguments()
    logger = get_logger(args.log_level)

    # Ensure the repository is supported.
    try:
        repo_type = repository.RepositoryType(args.repository)
    except ValueError:
        logger.error('Unsupported repository type %s.', args.repository)
        return

    # Ensure the platform is supported by the repository.
    repo = repository.RepositoryFactory.get_repository(repo_type)
    if args.platform not in repo.platforms():
        logger.error('Unsupported platform %s.', args.platform)
        return

    # Set the sections to be scanned.
    sections = args.section
    if not sections:
        sections = ['#'] + list(string.ascii_lowercase)

    # Set game tags that are allowed to be downloaded.
    allowed_tags = args.allow_tag
    if not allowed_tags:
        allowed_tags = []

    # Collect download statistics.
    games_downloaded = 0
    games_skipped = 0
    games_download_start = time.time()

    # Scan each section for games and download them.
    for section in sections:
        for game in repo.games(args.platform, section):
            # Check if the game is allowed to be downloaded.
            if not is_download_allowed(game, allowed_tags):
                games_skipped += 1
                logger.info('Skipping %s (%s)', game.name, ', '.join(game.tags))
                continue

            # Download the game.
            games_downloaded += 1
            download_start = time.time()
            if not args.pretend:
                retry_download(repo, game, args.retries)

            logger.info('Downloaded %s in %s.', game.name, get_download_duration(download_start))

    logger.info('Downloaded %d/%d games in %s.', games_downloaded, games_downloaded + games_skipped,
                get_download_duration(games_download_start))


if __name__ == '__main__':
    main()
