import os
import shutil
import tempfile
import unittest
import queue

from src.handler import AsyncIngestionHandler
from src.watch_manager import DynamicWatchManager

class TestWatchManager(unittest.TestCase):
    def setUp(self):
        self.test_dir_1 = tempfile.mkdtemp()
        self.test_dir_2 = tempfile.mkdtemp()
        self.work_queue = queue.Queue()
        self.handler = AsyncIngestionHandler(work_queue=self.work_queue)
        self.watch_manager = DynamicWatchManager(event_handler=self.handler)

    def tearDown(self):
        self.watch_manager.stop()
        shutil.rmtree(self.test_dir_1, ignore_errors=True)
        shutil.rmtree(self.test_dir_2, ignore_errors=True)

    def test_dynamic_watch_path_switching(self):
        self.watch_manager.start()
        
        # Set initial watch
        path1 = self.watch_manager.set_watch_directory(self.test_dir_1)
        self.assertEqual(os.path.abspath(self.test_dir_1), path1)
        self.assertEqual(self.watch_manager.get_current_directory(), path1)

        # Switch to second watch
        path2 = self.watch_manager.set_watch_directory(self.test_dir_2)
        self.assertEqual(os.path.abspath(self.test_dir_2), path2)
        self.assertEqual(self.watch_manager.get_current_directory(), path2)

if __name__ == "__main__":
    unittest.main()
