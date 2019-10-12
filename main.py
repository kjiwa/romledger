""""A program that downloads games from repositories such as Vimm's Lair and CoolROM.com."""

import argparse
import logging
import string
import time

import repository

SCRAPER_DEFAULT_SECTIONS = ['#'] + list(string.ascii_lowercase)
SCRAPER_LOG_FORMAT = '%(asctime)s - %(name)s.%(funcName)s - %(levelname)s - %(message)s'
SCRAPER_LOG_LEVELS = {'notset': logging.NOTSET, 'debug': logging.DEBUG, 'info': logging.INFO,
                      'warning': logging.WARNING, 'error': logging.ERROR, 'critical': logging.CRITICAL}


def get_logger(log_level):
    """Initializes and returns a logger instance.

    Args:
        log_level: The logging level.

    Returns:
        A logger instance.
    """
    logging.basicConfig(format=SCRAPER_LOG_FORMAT)
    logger = logging.getLogger()
    logger.setLevel(SCRAPER_LOG_LEVELS[log_level])
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


def retry_download(repo, game, retries, retry_delay):
    """Tries to download a game a specified number of times before failing.

    Args:
        repo: The repository from which to download the game.
        game: The game to be downloaded.
        retries: The number of times to try to download the game.
        retry_delay: The base number of seconds to wait between retries.

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

            # Implement exponential backoff between download attempts.
            time.sleep((2 ** i) * retry_delay)


def retry_scrape_section(repo, platform, section, retries, retry_delay):
    """Tries to scrape a repository section a specified number of times before failing.

    Args:
        repo: The repository from which to download the game.
        platform: The game platform to scrape.
        section: The section to scrape.
        retries: The number of times to try to download the game.
        retry_delay: The base number of seconds to wait between retries.

    Raises:
        GameScrapeException: The game could not be downloaded.
    """
    for i in range(0, retries):
        try:
            return repo.games(platform, section)
        except repository.GameScrapeException as ex:
            if i == retries - 1:
                raise ex

            # Implement exponential backoff between download attempts.
            time.sleep((2 ** i) * retry_delay)


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
                            help='The sections to scan for games. This option may be used multiple times.')
    repo_group.add_argument('--pretend', action='store_true', help='Whether to pretend downloading games.')
    repo_group.add_argument('--retries', default=3, type=int, help='The number of times to try to download a game.')
    repo_group.add_argument('--retry_delay', default=60, type=int,
                            help='The number of seconds to wait between retries.')
    repo_group.add_argument('--allow_tag', action='append',
                            help='Allow games with a tag to be downloaded. This option may be used multiple times.')

    # Logging arguments.
    logging_group = repo_group.add_argument_group('logging')
    logging_group.add_argument('--log_level', default='info',
                               choices=['notset', 'debug', 'info', 'warning', 'error', 'critical'],
                               help='The minimum log level to be displayed.')

    return parser.parse_args()


def main():
    """Parses program options and initiates game downloads."""
    args = parse_arguments()
    logger = get_logger(args.log_level)

    # Ensure the repository is supported.
    try:
        repo_type = repository.RepositoryType(args.repository)
    except ValueError:
        logger.error('Unsupported platform: %s.', args.platform)
        return

    # Ensure the platform is supported by the repository.
    repo = repository.RepositoryFactory.get_repository(repo_type)
    if args.platform not in repo.platforms():
        return

    # Set the sections to be scanned.
    sections = args.section
    if not sections:
        sections = SCRAPER_DEFAULT_SECTIONS

    # Set game tags that are allowed to be downloaded.
    allowed_tags = args.allow_tag
    if not allowed_tags:
        allowed_tags = []

    # Scan each section for games and download them.
    for section in sections:
        logger.info('Scraping section %s.', section)
        games = retry_scrape_section(repo, args.platform, section, args.retries, args.retry_delay)
        for game in games:
            # Check if the game is allowed to be downloaded.
            if not is_download_allowed(game, allowed_tags):
                logger.info('Skipping game "%s" (tags: %s).', game.name, ', '.join(game.tags))
                continue

            # Download the game.
            if not args.pretend:
                retry_download(repo, game, args.retries, args.retry_delay)

            logger.info('Downloaded game "%s"', game.name)


if __name__ == '__main__':
    main()
