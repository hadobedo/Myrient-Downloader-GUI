"""Unit tests for core.utils module."""

import os
import tempfile
import unittest

from core.utils import format_file_size, generate_unique_filename, generate_unique_dirname


class TestFormatFileSize(unittest.TestCase):
    """Tests for format_file_size()."""

    def test_zero_bytes(self):
        self.assertEqual(format_file_size(0), "0 B")

    def test_negative_treated_as_zero(self):
        self.assertEqual(format_file_size(-100), "0 B")

    def test_bytes(self):
        self.assertEqual(format_file_size(512), "512 B")

    def test_kilobytes(self):
        self.assertEqual(format_file_size(1024), "1.0 KB")
        self.assertEqual(format_file_size(1536), "1.5 KB")

    def test_megabytes(self):
        self.assertEqual(format_file_size(1024 * 1024), "1.0 MB")
        self.assertEqual(format_file_size(1024 * 1024 * 5), "5.0 MB")

    def test_gigabytes(self):
        self.assertEqual(format_file_size(1024 * 1024 * 1024), "1.00 GB")
        self.assertEqual(format_file_size(int(1024 * 1024 * 1024 * 2.5)), "2.50 GB")

    def test_boundary_values(self):
        self.assertEqual(format_file_size(1023), "1023 B")
        self.assertEqual(format_file_size(1024), "1.0 KB")
        self.assertEqual(format_file_size(1024 * 1024 - 1), "1024.0 KB")
        self.assertEqual(format_file_size(1024 * 1024), "1.0 MB")


class TestGenerateUniqueFilename(unittest.TestCase):
    """Tests for generate_unique_filename()."""

    def test_returns_numbered_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.iso")
            # File doesn't exist, so (1) should be returned
            open(path, "w").close()
            result = generate_unique_filename(path)
            self.assertEqual(result, os.path.join(tmp, "test (1).iso"))

    def test_increments_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Create original and (1)
            path = os.path.join(tmp, "game.zip")
            open(path, "w").close()
            open(os.path.join(tmp, "game (1).zip"), "w").close()
            result = generate_unique_filename(path)
            self.assertEqual(result, os.path.join(tmp, "game (2).zip"))


class TestGenerateUniqueDirname(unittest.TestCase):
    """Tests for generate_unique_dirname()."""

    def test_returns_numbered_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            dir_path = os.path.join(tmp, "GameFolder")
            os.makedirs(dir_path)
            result = generate_unique_dirname(dir_path)
            self.assertEqual(result, os.path.join(tmp, "GameFolder (1)"))

    def test_increments_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            dir_path = os.path.join(tmp, "MyGame")
            os.makedirs(dir_path)
            os.makedirs(os.path.join(tmp, "MyGame (1)"))
            result = generate_unique_dirname(dir_path)
            self.assertEqual(result, os.path.join(tmp, "MyGame (2)"))


if __name__ == "__main__":
    unittest.main()
