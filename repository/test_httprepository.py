import os
import os.path
import unittest

import repository

TEST_ROM_PLATFORM = 'NES'
TEST_ROM_SECTION = 'x'


class TestHttpRepository(unittest.TestCase):
    @staticmethod
    def get_repository():
        return repository.RepositoryFactory.get_repository(repository.RepositoryType.VIMMS_LAIR)

    def test_download_overwrites_existing_file_with_different_size(self):
        repo = self.get_repository()
        game = repo.games(TEST_ROM_PLATFORM, TEST_ROM_SECTION)[0]

        # Create 0 byte files for each game file.
        for gamefile in game.files:
            path = '{}/{}'.format(game.platform, gamefile.filename)
            os.mkdir(game.platform)
            open(path, 'w').close()
            self.assertEqual(os.path.getsize(path), 0)

        # Download the file and ensure it is greater than 0 bytes.
        repo.download(game)
        for gamefile in game.files:
            path = '{}/{}'.format(game.platform, gamefile.filename)
            try:
                self.assertTrue(os.path.isfile(path))
                self.assertGreater(os.path.getsize(path), 0)
            finally:
                if os.path.isfile(path):
                    os.unlink(path)
                    os.rmdir(game.platform)

    def test_download_skips_existing_file_with_same_size(self):
        repo = self.get_repository()
        game = repo.games(TEST_ROM_PLATFORM, TEST_ROM_SECTION)[0]

        # Create zero-filled files for each game file.
        mtime = None
        for gamefile in game.files:
            path = '{}/{}'.format(game.platform, gamefile.filename)
            os.mkdir(game.platform)
            f = open(path, 'wb')
            f.seek(gamefile.size_bytes - 1)
            f.write(b'\0')
            f.close()

            mtime = os.path.getmtime(path)
            self.assertEqual(os.path.getsize(path), gamefile.size_bytes)

        # Download the file and ensure its modification time is unchanged.
        repo.download(game)
        for gamefile in game.files:
            path = '{}/{}'.format(game.platform, gamefile.filename)
            try:
                self.assertEqual(os.path.getmtime(path), mtime)
            finally:
                if os.path.isfile(path):
                    os.unlink(path)
                    os.rmdir(game.platform)
