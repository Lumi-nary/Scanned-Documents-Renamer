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

if __name__ == "__main__":
    unittest.main()
