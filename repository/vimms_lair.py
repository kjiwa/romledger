"""A module for accessing games on Vimm's Lair."""

import re

import lxml.html
import requests

from repository import model

VIMMS_VAULT_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0) Chrome/75.0.3770.142'}
VIMMS_VAULT_SECTION_URL = 'https://vimm.net/vault/?p=list&system=%s&section=%s'
VIMMS_VAULT_GAME_URL_REGEX = re.compile(r'^/vault/(\d+)$')
VIMMS_VAULT_GAME_URL = 'https://vimm.net/vault/%s'
VIMMS_VAULT_GAME_DOWNLOAD_URL = 'https://download2.vimm.net/download.php?id=%s&t1=%s&t2=%s&download=Download'


class VimmsLairRepository(model.Repository):
    """A class for interacting with Vimm's Lair games."""

    @staticmethod
    def platforms():
        return ['DS', 'Dreamcast', 'GB', 'GBA', 'GBC', 'GameCube', 'Genesis', 'N64', 'NES', 'PS1', 'PS2', 'PSP', 'SNES',
                'Wii']

    @staticmethod
    def games(platform, section):
        if section == '#':
            section = 'number'

        response = requests.get(VIMMS_VAULT_SECTION_URL % (platform, section), headers=VIMMS_VAULT_HEADERS)
        if response.status_code != 200:
            raise RuntimeError(response.content)

        tree = lxml.html.fromstring(response.content)
        items = tree.xpath('//div[@id="innerMain"]//tr/td[a]')
        games = []
        for i in items:
            game_id = VimmsLairRepository._game_id(i)
            if not game_id:
                continue

            game_name = i.find('a').text
            game_tags = [i.text for i in i.findall('b')]
            game_url = VimmsLairRepository._game_url(game_id, game_name)
            games.append(model.Game(game_id, platform, game_name, game_tags, game_url))

        return games

    @staticmethod
    def download(game, headers=None):
        return model.Repository.download(game, headers=VIMMS_VAULT_HEADERS)

    @staticmethod
    def _game_id(element):
        matches = VIMMS_VAULT_GAME_URL_REGEX.match(element.find('a').get('href'))
        if not matches:
            return None

        return matches.group(1)

    @staticmethod
    def _game_url(game_id, game_name):
        response = requests.get(VIMMS_VAULT_GAME_URL % game_id, headers=VIMMS_VAULT_HEADERS)
        if response.status_code != 200:
            raise RuntimeError(response.content)

        tree = lxml.html.fromstring(response.content)
        if not tree.xpath('//input[@value="Download"]'):
            raise model.GameDownloadException('No download link for %s' % game_name)

        game_id = tree.xpath('//input[@name="mediaId"]')[0].get('value')
        game_t1 = tree.xpath('//input[@name="t1"]')[0].get('value')
        game_t2 = tree.xpath('//input[@name="t2"]')[0].get('value')
        return VIMMS_VAULT_GAME_DOWNLOAD_URL % (game_id, game_t1, game_t2)
