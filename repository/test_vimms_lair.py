import os
import os.path
import unittest

import repository

TEST_ROM_FILENAME = 'NES/Xenophobe.zip'
TEST_ROM_PLATFORM = 'NES'
TEST_ROM_SECTION = 'x'


class TestVimmsLairRepository(unittest.TestCase):
    @staticmethod
    def get_repository():
        return repository.RepositoryFactory.get_repository(repository.RepositoryType.VIMMS_LAIR)

    def test_platforms(self):
        self.assertTrue(self.get_repository().platforms())

    def test_games(self):
        self.assertTrue(self.get_repository().games(TEST_ROM_PLATFORM, TEST_ROM_SECTION))

    def test_size(self):
        games = self.get_repository().games(TEST_ROM_PLATFORM, TEST_ROM_SECTION)
        for game in games:
            self.assertGreater(game.size_bytes, 0)

    def test_download(self):
        repo = self.get_repository()
        repo.download(repo.games(TEST_ROM_PLATFORM, TEST_ROM_SECTION)[0])

        try:
            self.assertTrue(os.path.isfile(TEST_ROM_FILENAME))
        finally:
            if os.path.isfile(TEST_ROM_FILENAME):
                os.unlink(TEST_ROM_FILENAME)
                os.rmdir(TEST_ROM_PLATFORM)
