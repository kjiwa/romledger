import os
import os.path
import unittest

import repository

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

    def test_games_without_download_tables(self):
        repo = self.get_repository()
        games = repo.games('N64', 'a')
        game = [i for i in games if i.name == 'Aidyn Chronicles: The First Mage'][0]
        self.assertEqual(len(game.files), 1)

    def test_games_with_multiple_files(self):
        repo = self.get_repository()
        games = repo.games('GameCube', 'b')
        game = [i for i in games if i.name == 'Baten Kaitos Origins'][0]
        self.assertEqual(len(game.files), 2)

    def test_wii_games_have_info(self):
        repo = self.get_repository()
        games = repo.games('Wii', '#')
        self.assertGreater(len(games), 0)
