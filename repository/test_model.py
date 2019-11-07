import unittest

import repository


class TestModel(unittest.TestCase):
    def test_game_files_with_different_extensions_are_equal(self):
        gf1 = repository.GameFile('filename.with.dots.7z', 0, 'some://url')
        gf2 = repository.GameFile('filename.with.dots.zip', 1, 'some://other.url')
        self.assertEqual(gf1, gf2)
