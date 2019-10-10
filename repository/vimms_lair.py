"""A module for accessing games on Vimm's Lair."""

import re
import urllib.parse

import lxml.html
import requests

from repository import model

VIMMS_VAULT_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0) Chrome/75.0.3770.142'}
VIMMS_VAULT_SECTION_URL = 'https://vimm.net/vault/?p=list&system={}&section={}'
VIMMS_VAULT_GAME_URL_REGEX = re.compile(r'^/vault/(\d+)$')
VIMMS_VAULT_GAME_URL = 'https://vimm.net/vault/{}'
VIMMS_VAULT_GAME_DOWNLOAD_URL = 'https://download2.vimm.net/download.php?'


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

        response = requests.get(VIMMS_VAULT_SECTION_URL.format(platform, section), headers=VIMMS_VAULT_HEADERS)
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
            game_urls = VimmsLairRepository._game_urls(game_id, game_name)
            game_size = VimmsLairRepository._game_size(game_urls)
            games.append(model.Game(game_id, platform, game_name, game_size, game_tags, game_urls))

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
    def _game_size(game_urls):
        size = 0
        for url in game_urls:
            response = requests.get(url, headers=VIMMS_VAULT_HEADERS, stream=True)
            if response.status_code != 200:
                raise RuntimeError(response)

            size += int(response.headers['Content-length'])
            response.close()

        return size

    @staticmethod
    def _game_urls(game_id, game_name):
        response = requests.get(VIMMS_VAULT_GAME_URL.format(game_id), headers=VIMMS_VAULT_HEADERS)
        if response.status_code != 200:
            raise RuntimeError(response.content)

        tree = lxml.html.fromstring(response.content)
        if not tree.xpath('//input[@value="Download"]'):
            raise model.GameDownloadException('No download link for {}'.format(game_name))

        urls = []
        rows = tree.xpath('//table[@id="downloadTable1"]//tr')
        for row in rows:
            inputs = row.xpath('.//input')
            query = {i.name: i.get('value') for i in inputs}
            urls.append('{}{}'.format(VIMMS_VAULT_GAME_DOWNLOAD_URL, urllib.parse.urlencode(query)))

        return urls
