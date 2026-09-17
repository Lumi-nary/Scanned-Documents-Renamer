import os
import shutil
import tempfile
import unittest
import time

from src.config import PipelineConfig
from src.pipeline_daemon import PipelineDaemon

class TestPipelineDaemon(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.watch_dir = os.path.join(self.temp_dir, "Temporary")
        os.makedirs(self.watch_dir, exist_ok=True)
        
        self.config = PipelineConfig(
            watch_directories=[self.watch_dir],
            provider="openrouter",
            api_key="your-api-key-here",
            num_workers=1,
            stability_timeout=1
        )
        self.daemon = PipelineDaemon(config=self.config)

    def tearDown(self):
        if self.daemon.is_running:
            self.daemon.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_daemon_lifecycle(self):
        events = []
        self.daemon.add_listener(lambda e: events.append(e))

        status_initial = self.daemon.get_status()
        self.assertFalse(status_initial["is_running"])

        # Start in mock mode
        started = self.daemon.start(mock_mode=True)
        self.assertTrue(started)
        self.assertTrue(self.daemon.is_running)

        status_running = self.daemon.get_status()
        self.assertTrue(status_running["is_running"])

        # Stop
        stopped = self.daemon.stop()
        self.assertTrue(stopped)
        self.assertFalse(self.daemon.is_running)

        # Check that events were emitted
        self.assertTrue(any(e.get("category") == "status" for e in events))

    def test_active_client_context(self):
        self.daemon.start(mock_mode=True)
        self.daemon.set_active_client("Acme Corp")
        self.assertEqual(self.daemon.get_active_client(), "Acme Corp")

        self.daemon.reset_active_client()
        self.assertIsNone(self.daemon.get_active_client())
        self.daemon.stop()

    def test_config_save_and_reload(self):
        settings_path = os.path.join(self.temp_dir, "custom_settings.json")
        self.config.provider = "deepseek"
        self.config.model_name = "deepseek-chat"
        self.config.save(settings_path)

        loaded = PipelineConfig.load(settings_path)
        self.assertEqual(loaded.provider, "deepseek")
        self.assertEqual(loaded.model_name, "deepseek-chat")
    def test_recursive_watch_folder_scan(self):
        # Create nested subdirectories with a document
        sub_dir = os.path.join(self.watch_dir, "2026-Batch", "Unprocessed")
        os.makedirs(sub_dir, exist_ok=True)
        test_file = os.path.join(sub_dir, "invoice_001.pdf")
        with open(test_file, "w") as f:
            f.write("%PDF-1.4 dummy content")

        enqueued = self.daemon.scan_watched_folder()
        self.assertIn(test_file, enqueued)

    def test_update_watch_directories_auto_scan(self):
        self.daemon.start(mock_mode=True)
        # Create a new separate watch directory with files
        new_watch = os.path.join(self.temp_dir, "NewFolder", "SubBatch")
        os.makedirs(new_watch, exist_ok=True)
        new_file = os.path.join(new_watch, "scanned_doc.pdf")
        with open(new_file, "w") as f:
            f.write("%PDF-1.4 new scan content")

        enqueued = self.daemon.update_watch_directories([new_watch])
        self.assertIn(new_file, enqueued)
        self.daemon.stop()

    def test_client_directories_deep_discovery(self):
        clients_root = os.path.join(self.temp_dir, "ClientsRoot")
        os.makedirs(os.path.join(clients_root, "Litigation", "Pacific Trading Corp"), exist_ok=True)
        os.makedirs(os.path.join(clients_root, "Finance", "Box 1", "Solar Power Inc"), exist_ok=True)
        os.makedirs(os.path.join(clients_root, "Direct Client Corp"), exist_ok=True)

        self.daemon.update_clients_directory(clients_root)
        discovered = self.daemon.get_client_directories()

        self.assertIn("Pacific Trading Corp", discovered)
        self.assertIn("Solar Power Inc.", discovered)
        self.assertIn("Direct Client Corp", discovered)
        self.assertIn("General Clients", discovered)

if __name__ == "__main__":
    unittest.main()

