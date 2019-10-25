"""A module for accessing CoolROM.com games.

Games in the CoolROM repository are typically tagged with a region code, such as Europe, Japan, or
USA.
"""

import re

import lxml.html
import requests

from repository import model
from .http_repository import HttpRepository

COOLROM_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0) Chrome/75.0.3770.142'}
COOLROM_HOME_URL = 'https://coolrom.com.au/roms/'
COOLROM_SECTION_URL = 'https://coolrom.com.au/roms/{}/{}/'
COOLROM_GAME_URL = 'https://coolrom.com.au/dlpop.php?id={}'
COOLROM_PLATFORM_URL_REGEX = re.compile(r'^/roms/(.+)/$')
COOLROM_GAME_URL_REGEX = re.compile(r'^/roms/\S+/(\d+)/.+.php$')
COOLROM_GAME_FILENAME_REGEX = re.compile(r'^attachment; filename="(\S+)"$')


class CoolRomRepository(HttpRepository):
    """A class for interacting with CoolROM.com games."""

    def __init__(self, proxy_type, proxy_host, proxy_port, proxy_user, proxy_password):
        super().__init__(
            COOLROM_HEADERS, proxy_type, proxy_host, proxy_port, proxy_user, proxy_password)

    def platforms(self):
        response = requests.get(COOLROM_HOME_URL, proxies=self._proxies)
        if response.status_code != 200:
            raise model.GameScrapeException('Unable to scan platforms: {}'.format(response.content))

        tree = lxml.html.fromstring(response.content)
        items = tree.xpath('//a[@href]')
        platforms = []
        for i in items:
            url = i.get('href')
            matches = COOLROM_PLATFORM_URL_REGEX.match(url)
            if not matches:
                continue

            platforms.append(matches.group(1))

        return platforms

    def games(self, platform, section):
        if section == '#':
            section = '0'

        response = requests.get(
            COOLROM_SECTION_URL.format(platform, section), proxies=self._proxies)
        if response.status_code != 200:
            raise model.GameScrapeException(
                'Unable to scan section {}: {}'.format(section, response.content))

        tree = lxml.html.fromstring(response.content)
        items = tree.xpath('//font/font/div[a[@href]]')
        games = []
        for i in items:
            game_id = CoolRomRepository._game_id(i)
            if not game_id:
                continue

            game_name = i.find('a').text
            game_tags = [i.get('class')]
            game_files = set([self._game_file(game_name, self._game_url(game_name, game_id))])
            games.append(model.Game(game_id, platform, game_name, game_tags, game_files))

        return games

    @staticmethod
    def _game_id(element):
        matches = COOLROM_GAME_URL_REGEX.match(element.find('a').get('href'))
        return matches.group(1) if matches else None

    def _game_url(self, game_name, game_id):
        response = requests.get(COOLROM_GAME_URL.format(game_id), proxies=self._proxies)
        if response.status_code != 200:
            raise model.GameScrapeException(
                'Unable to get URL for {}: {}'.format(game_name, response.content))

        contents = response.content.decode()
        return contents.split('form method="POST" action="')[1].split('"')[0]

    def _game_file(self, game_name, game_url):
        response = requests.head(game_url, proxies=self._proxies)
        if response.status_code != 200:
            raise model.GameScrapeException(
                'Unable to get file information for {}: {}'.format(game_name, response.content))

        return model.GameFile(
            COOLROM_GAME_FILENAME_REGEX.match(response.headers['Content-Disposition']).group(1),
            int(response.headers['Content-Length']), game_url)
