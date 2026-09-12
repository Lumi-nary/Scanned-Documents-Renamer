import os
import time
import queue
import shutil
import tempfile
import threading
import unittest

from src.config import PipelineConfig
from src.handler import AsyncIngestionHandler
from src.dispatcher import AIAPIDispatcher
from src.watch_manager import DynamicWatchManager
from src.worker import worker_loop

class TestPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.watch_dir_1 = tempfile.mkdtemp()
        self.watch_dir_2 = tempfile.mkdtemp()
        self.output_dir = tempfile.mkdtemp()

        self.config = PipelineConfig(
            watch_directory=self.watch_dir_1,
            stability_timeout=5,
            stability_poll_interval=0.1,
            api_key="mock-key",
            num_workers=1
        )
        self.work_queue = queue.Queue()
        self.stop_event = threading.Event()

        self.dispatcher = AIAPIDispatcher(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            model_name=self.config.model_name,
            mock_mode=True
        )

        self.handler = AsyncIngestionHandler(
            work_queue=self.work_queue,
            allowed_extensions=self.config.allowed_extensions,
            ignored_extensions=self.config.ignored_extensions
        )

        self.watch_manager = DynamicWatchManager(event_handler=self.handler)
        self.watch_manager.set_watch_directory(self.watch_dir_1)
        self.watch_manager.start()

        self.worker_thread = threading.Thread(
            target=worker_loop,
            args=(self.work_queue, self.dispatcher, self.stop_event, self.config, self.output_dir),
            name="TestWorker-1",
            daemon=True
        )
        self.worker_thread.start()

    def tearDown(self):
        self.stop_event.set()
        self.watch_manager.stop()
        shutil.rmtree(self.watch_dir_1, ignore_errors=True)
        shutil.rmtree(self.watch_dir_2, ignore_errors=True)
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def test_end_to_end_file_ingestion(self):
        test_file_path = os.path.join(self.watch_dir_1, "sample_document.txt")
        
        # Create file in watch directory 1
        with open(test_file_path, "w", encoding="utf-8") as f:
            f.write("Sample document payload for integration testing.")

        # Wait for file processing
        max_wait = 5.0
        start = time.time()
        output_file = os.path.join(self.output_dir, "sample_document.txt.response.txt")

        while time.time() - start < max_wait:
            if os.path.exists(output_file):
                break
            time.sleep(0.2)

        self.assertTrue(os.path.exists(output_file), "AI response output file was not generated.")

        with open(output_file, "r", encoding="utf-8") as f:
            res_content = f.read()

        self.assertIn("Mock AI Summary", res_content)

    def test_dynamic_directory_migration(self):
        # Migrate watch directory to watch_dir_2
        self.watch_manager.set_watch_directory(self.watch_dir_2)
        time.sleep(0.5)

        test_file_path = os.path.join(self.watch_dir_2, "migrated_file.json")
        with open(test_file_path, "w", encoding="utf-8") as f:
            f.write('{"title": "migrated test payload"}')

        max_wait = 5.0
        start = time.time()
        output_file = os.path.join(self.output_dir, "migrated_file.json.response.txt")

        while time.time() - start < max_wait:
            if os.path.exists(output_file):
                break
            time.sleep(0.2)

        self.assertTrue(os.path.exists(output_file), "Migrated file response was not generated.")

    def test_direct_routing_and_sticky_client_pipeline(self):
        from src.client_manager import ClientManager
        import fitz

        unproc_dir = os.path.join(self.watch_dir_1, "Temporary", "Unproccesed")
        os.makedirs(unproc_dir, exist_ok=True)
        client_mgr = ClientManager(unproc_dir)

        # Stop the default worker and launch one with client_mgr
        self.stop_event.set()
        self.worker_thread.join()

        new_stop_event = threading.Event()
        routed_worker = threading.Thread(
            target=worker_loop,
            args=(self.work_queue, self.dispatcher, new_stop_event, self.config, self.output_dir, None, client_mgr),
            name="RoutedWorker",
            daemon=True
        )
        routed_worker.start()

        try:
            # File 1: Secretary's Certificate with GLOBAL GROUP CORPORATION
            pdf1_path = os.path.join(unproc_dir, "scan01.pdf")
            doc1 = fitz.open()
            page1 = doc1.new_page()
            page1.insert_textbox(fitz.Rect(50, 50, 550, 200), 'I, JUAN DELA CRUZ, Filipino, of legal age, being the Corporate Secretary of GLOBAL GROUP CORPORATION (the "Corporation"), a corporation duly organized...')
            doc1.save(pdf1_path)
            doc1.close()

            # Wait for File 1 to be routed automatically by watchdog
            max_wait = 8.0
            start = time.time()
            expected_folder_1 = os.path.join(client_mgr.root_dir, "Global Group Corporation")
            while time.time() - start < max_wait:
                if os.path.exists(expected_folder_1) and len(os.listdir(expected_folder_1)) > 0:
                    break
                time.sleep(0.2)

            self.assertTrue(os.path.exists(expected_folder_1))
            self.assertEqual(client_mgr.get_active_client(), "Global Group Corporation")

            # File 2: Supporting document with NO client name (attachment / receipt)
            pdf2_path = os.path.join(unproc_dir, "scan02.pdf")
            doc2 = fitz.open()
            page2 = doc2.new_page()
            page2.insert_textbox(fitz.Rect(50, 50, 550, 200), 'Out-of-Pocket Expenses Official Receipt\nDate: 09/10/2024\nAmount: 1500.00')
            doc2.save(pdf2_path)
            doc2.close()

            # Wait for File 2 to be routed to Global Group Corporation via sticky context
            start = time.time()
            while time.time() - start < max_wait:
                if len(os.listdir(expected_folder_1)) >= 2:
                    break
                time.sleep(0.2)

            files_in_client_dir = os.listdir(expected_folder_1)
            self.assertGreaterEqual(len(files_in_client_dir), 2)
            self.assertFalse(os.path.exists(pdf1_path))
            self.assertFalse(os.path.exists(pdf2_path))

        finally:
            new_stop_event.set()
            routed_worker.join()

if __name__ == "__main__":
    unittest.main()
