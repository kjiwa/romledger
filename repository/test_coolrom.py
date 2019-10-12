import os
import os.path
import unittest

import repository

TEST_ROM_PLATFORM = 'atari7800'
TEST_ROM_SECTION = 'x'


class TestCoolRomRepository(unittest.TestCase):
    @staticmethod
    def get_repository():
        return repository.RepositoryFactory.get_repository(repository.RepositoryType.COOLROM)

    def test_platforms(self):
        self.assertTrue(self.get_repository().platforms())

    def test_games(self):
        self.assertTrue(self.get_repository().games(TEST_ROM_PLATFORM, TEST_ROM_SECTION))

    def test_size(self):
        games = self.get_repository().games(TEST_ROM_PLATFORM, TEST_ROM_SECTION)
        for game in games:
            for gamefile in game.files:
                self.assertGreater(gamefile.size_bytes, 0)

    def test_download(self):
        repo = self.get_repository()
        game = repo.games(TEST_ROM_PLATFORM, TEST_ROM_SECTION)[0]
        repo.download(game)

        for gamefile in game.files:
            path = '{}/{}'.format(game.platform, gamefile.filename)
            try:
                self.assertTrue(os.path.isfile(path))
            finally:
                if os.path.isfile(path):
                    os.unlink(path)
                    os.rmdir(game.platform)
