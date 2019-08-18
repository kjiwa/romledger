"""A module for accessing CoolROM.com games.

Games in the CoolROM repository are typically tagged with a region code, such as Europe, Japan, or USA.
"""

import re

import lxml.html
import requests

from repository import model

COOLROM_HOME_URL = 'https://coolrom.com.au/roms/'
COOLROM_SECTION_URL = 'https://coolrom.com.au/roms/%s/%s/'
COOLROM_GAME_URL = 'https://coolrom.com.au/dlpop.php?id=%s'
COOLROM_PLATFORM_URL_REGEX = re.compile(r'^/roms/(.+)/$')
COOLROM_GAME_URL_REGEX = re.compile(r'^/roms/\S+/(\d+)/.+.php$')


class CoolRomRepository(model.Repository):
    """A class for interacting with CoolROM.com games."""

    @staticmethod
    def platforms():
        response = requests.get(COOLROM_HOME_URL)
        if response.status_code != 200:
            raise RuntimeError(response.content)

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

    @staticmethod
    def games(platform, section):
        if section == '#':
            section = '0'

        response = requests.get(COOLROM_SECTION_URL % (platform, section))
        if response.status_code != 200:
            raise RuntimeError(response.content)

        tree = lxml.html.fromstring(response.content)
        items = tree.xpath('//font/font/div[a[@href]]')
        games = []
        for i in items:
            game_id = CoolRomRepository._game_id(i)
            if not game_id:
                continue

            game_name = i.find('a').text
            game_tags = [i.get('class')]
            game_url = CoolRomRepository._game_url(game_id)
            games.append(model.Game(game_id, platform, game_name, game_tags, game_url))

        return games

    @staticmethod
    def _game_id(element):
        matches = COOLROM_GAME_URL_REGEX.match(element.find('a').get('href'))
        return matches.group(1) if matches else None

    @staticmethod
    def _game_url(game_id):
        response = requests.get(COOLROM_GAME_URL % game_id)
        if response.status_code != 200:
            raise RuntimeError(response.content)

        contents = response.content.decode()
        return contents.split('form method="POST" action="')[1].split('"')[0]
