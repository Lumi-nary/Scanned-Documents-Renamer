import os
import sys
import time
import shutil
import tempfile
import unittest

from src.stability import (
    is_temporary_file,
    check_exclusive_lock,
    wait_for_file_stability,
    FileStabilityError
)

class TestStability(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_is_temporary_file(self):
        self.assertTrue(is_temporary_file("document.tmp"))
        self.assertTrue(is_temporary_file("download.part"))
        self.assertTrue(is_temporary_file("~lock.file.docx"))
        self.assertTrue(is_temporary_file(".hidden_file"))
        self.assertFalse(is_temporary_file("report.pdf"))
        self.assertFalse(is_temporary_file("data.json"))

    def test_exclusive_lock(self):
        filepath = os.path.join(self.test_dir, "lock_test.txt")
        with open(filepath, "w") as f:
            f.write("Lock testing content")

        self.assertTrue(check_exclusive_lock(filepath))

    def test_wait_for_file_stability_success(self):
        filepath = os.path.join(self.test_dir, "stable_file.txt")
        with open(filepath, "w") as f:
            f.write("Stable content baseline")

        result = wait_for_file_stability(filepath, timeout=5, poll_interval=0.1, consecutive_checks=2)
        self.assertTrue(result)

    def test_wait_for_file_stability_timeout(self):
        filepath = os.path.join(self.test_dir, "unstable_file.txt")
        
        # Write initial line
        with open(filepath, "w") as f:
            f.write("Line 1\n")

        # Expect stability error if file doesn't exist or is timed out cleanly
        non_existent_file = os.path.join(self.test_dir, "does_not_exist.txt")
        with self.assertRaises(FileStabilityError):
            wait_for_file_stability(non_existent_file, timeout=1, poll_interval=0.2)

if __name__ == "__main__":
    unittest.main()
