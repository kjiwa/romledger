"""A module for accessing games on Vimm's Lair.

The maintainer of Vimm's Lair has gone to lengths to prevent bots from scraping site content and
downloading its game catalog. Clients wishing to scrape game data must identify themselves as a
valid web browser (such as Chrome, Firefox, or Internet Explorer). Download requests are further
complicated by requiring clients submit a valid referrer and the correct input keys for each file.

Vimm's Lair supports the following game tags:
  H: hacked
  T: translated
  U: unlicensed
"""

import re
import urllib.parse

import lxml.html

from repository import model
from .http_repository import HttpRepository

VIMMS_VAULT_HEADERS = {
    'Accept': '*/*',
    'Connection': 'keep-alive',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0) Chrome/75.0.3770.142'
}

VIMMS_VAULT_BASE_URL = 'https://vimm.net'
VIMMS_VAULT_SECTION_URL = VIMMS_VAULT_BASE_URL + '/vault/?p=list&system={}&section={}'
VIMMS_VAULT_GAME_URL_REGEX = re.compile(r'^/vault/(\d+)$')
VIMMS_VAULT_GAME_URL = VIMMS_VAULT_BASE_URL + '/vault/{}'


class VimmsLairRepository(HttpRepository):
    """A class for interacting with Vimm's Lair games."""

    def __init__(
            self, retries, retry_delay, proxy_type, proxy_host, proxy_port, proxy_user,
            proxy_password, chunk_size, timeout):
        super().__init__(
            VIMMS_VAULT_HEADERS, retries, retry_delay, proxy_type, proxy_host, proxy_port,
            proxy_user, proxy_password, chunk_size, timeout)

    def platforms(self):
        return [
            'DS', 'Dreamcast', 'GB', 'GBA', 'GBC', 'GameCube', 'Genesis', 'N64', 'NES', 'PS1',
            'PS2', 'PSP', 'SNES', 'Wii']

    def games(self, platform, section):
        if section == '#':
            section = 'number'

        response = self.retry_get_request(VIMMS_VAULT_SECTION_URL.format(platform, section))
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
            game_files = set()
            for url in self._game_urls(game_id, game_name):
                try:
                    game_files.add(self._game_file(game_id, game_name, url))
                except model.GameScrapeException:
                    # Ignore erroneous download links.
                    continue

            games.append(model.Game(game_id, platform, game_name, game_tags, game_files))

        return games

    @staticmethod
    def _game_id(element):
        matches = VIMMS_VAULT_GAME_URL_REGEX.match(element.find('a').get('href'))
        if not matches:
            return None

        return matches.group(1)

    def _game_urls(self, game_id, game_name):
        response = self.retry_get_request(VIMMS_VAULT_GAME_URL.format(game_id))
        if response.status_code != 200:
            raise RuntimeError(response.content)

        # Some download links are not encapsulated in a table (e.g. "Aidyn Chronicles: The First
        # Mage" for Nintendo DS). In this case, fall back to searching for download forms.
        #
        # Searching for download forms is not the default behavior to prevent excessive downloads,
        # such as in the case of "Baten Kaitos Origins," which has four images: two for the
        # scrubbed version of the game, and two for the redump.
        tree = lxml.html.fromstring(response.content)
        rows = tree.xpath('//table[@id="downloadTable1"]//form[@method="GET"]')
        if not rows:
            rows = tree.xpath('//div[@id="innerMain"]//form[@method="GET"]')

        urls = []
        for row in rows:
            url = VimmsLairRepository._game_url_from_form_action(row.get('action'))
            inputs = row.xpath('.//input')
            query = {i.name: i.get('value') for i in inputs}
            urls.append('{}?{}'.format(url, urllib.parse.urlencode(query)))

        return urls

    def _game_file(self, game_id, game_name, game_url):
        # Some downloads require a "Referer" header for a successful server response.
        additional_headers = {'Referer': VIMMS_VAULT_GAME_URL.format(game_id)}

        # Some HEAD requests (such as those to downloads hosted in Google Drive) will fail. In
        # those cases, a streaming GET can be used to get game file information. Since HEAD
        # requests are faster, they are preferred and tried first.
        response = self.retry_head_request(game_url, additional_headers=additional_headers)
        if response.status_code != 200:
            response = self.retry_get_request(
                game_url, stream=True, additional_headers=additional_headers)
            if response.status_code != 200:
                raise model.GameScrapeException(
                    'Unable to get file information for {}: {}'.format(game_name, response.content))

        # Some download links are broken and point to non-existent links. In those cases, a filename
        # cannot be determined.
        if 'Content-Disposition' not in response.headers:
            raise model.GameScrapeException('Unable to get filename for {}'.format(game_name))

        filename = VimmsLairRepository._game_filename(
            game_name, response.headers['Content-Disposition'])

        size_bytes = None
        if 'Content-Length' in response.headers:
            size_bytes = int(response.headers['Content-Length'])

        response.close()

        return model.GameFile(filename, size_bytes, response.url)

    @staticmethod
    def _game_filename(game_name, content_disposition):
        parts = [s.strip() for s in content_disposition.split(';')]
        for s in parts:
            if not s.startswith('filename'):
                continue

            subparts = s.split('=')
            if subparts[0] == 'filename':
                return subparts[1][1:-1]

        raise model.GameScrapeException(
            'Unable to determine filename for {}: {}'.format(game_name, content_disposition))

    @staticmethod
    def _game_url_from_form_action(action):
        # Form actions on Vimm's Lair can be one of the following:
        # - //download.vimm.net/download.php
        # - //download2.vimm.net/download.php
        # - /mirror.php
        if action.startswith('//'):
            return 'https:{}'.format(action)

        return '{}{}'.format(VIMMS_VAULT_BASE_URL, action)
