import os
import os.path
import unittest

import repository


class TestVimmsLairRepository(unittest.TestCase):
    @staticmethod
    def get_repository():
        return repository.RepositoryFactory.get_repository(repository.RepositoryType.VIMMS_LAIR)

    def test_platforms(self):
        self.assertTrue(self.get_repository().platforms())

    def test_games(self):
        self.assertTrue(self.get_repository().games('NES', 'x'))

    def test_download(self):
        repo = self.get_repository()
        repo.download(repo.games('NES', 'x')[0])

        try:
            self.assertTrue(os.path.isfile('NES/Xenophobe.zip'))
        finally:
            if os.path.isfile('NES/Xenophobe.zip'):
                os.unlink('NES/Xenophobe.zip')
                os.rmdir('NES')
