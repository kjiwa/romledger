import os
import os.path
import unittest

import repository


class TestCoolRomRepository(unittest.TestCase):
    @staticmethod
    def get_repository():
        return repository.RepositoryFactory.get_repository(repository.RepositoryType.COOLROM)

    def test_platforms(self):
        self.assertTrue(self.get_repository().platforms())

    def test_games(self):
        self.assertTrue(self.get_repository().games('atari2600', 'a'))

    def test_download(self):
        game = repository.Game('16080', 'atari2600', 'Pac-Man', ['USA'],
                               'http://dl.coolrom.com.au/dl/16080/x0MQ-vo6cramrV-pcqENXw/1566159911/')
        self.get_repository().download(game)

        try:
            self.assertTrue(os.path.isfile('atari2600/Pac-Man.zip'))
        finally:
            if os.path.isfile('atari2600/Pac-Man.zip'):
                os.unlink('atari2600/Pac-Man.zip')
                os.rmdir('atari2600')
