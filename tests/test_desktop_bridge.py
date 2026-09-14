import os
import shutil
import tempfile
import unittest

from src.config import PipelineConfig
from src.pipeline_daemon import PipelineDaemon
from app import DesktopBridgeAPI

class TestDesktopBridgeAPI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.settings_file = os.path.join(self.temp_dir, "test_settings.json")
        self.watch_dir = os.path.join(self.temp_dir, "Watch")
        os.makedirs(self.watch_dir, exist_ok=True)

        self.config = PipelineConfig(
            watch_directories=[self.watch_dir],
            provider="mock",
            api_key="mock-key",
            num_workers=1,
            stability_timeout=1
        )
        self.config.save(self.settings_file)

        self.daemon = PipelineDaemon(config=self.config, settings_file=self.settings_file)
        self.api = DesktopBridgeAPI(daemon=self.daemon, settings_file=self.settings_file)

    def tearDown(self):
        if self.daemon.is_running:
            self.daemon.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_initial_data(self):
        data = self.api.get_initial_data()
        self.assertIn("status", data)
        self.assertIn("settings", data)
        self.assertIn("recent_records", data)
        self.assertFalse(data["status"]["is_running"])
        self.assertEqual(data["settings"]["provider"], "mock")

    def test_save_settings(self):
        new_settings = {
            "watch_directories": [self.watch_dir],
            "provider": "deepseek",
            "model_name": "deepseek-chat",
            "api_key": "sk-12345",
            "num_workers": 4,
            "stability_timeout": 15,
            "enable_wrapup": True,
            "update_clients_docx": True
        }
        res = self.api.save_settings(new_settings)
        self.assertTrue(res["success"])

        # Verify disk persistence
        loaded = PipelineConfig.load(self.settings_file)
        self.assertEqual(loaded.provider, "deepseek")
        self.assertEqual(loaded.api_key, "sk-12345")
        self.assertEqual(loaded.num_workers, 4)
        self.assertTrue(loaded.enable_wrapup)

    def test_pipeline_control(self):
        start_res = self.api.start_pipeline()
        self.assertTrue(start_res["success"])
        self.assertTrue(self.daemon.is_running)

        stop_res = self.api.stop_pipeline()
        self.assertTrue(stop_res["success"])
        self.assertFalse(self.daemon.is_running)

    def test_active_client_methods(self):
        self.api.start_pipeline()
        self.api.set_active_client("Pacific Heights")
        self.assertEqual(self.daemon.get_active_client(), "Pacific Heights")

        self.api.reset_active_client()
        self.assertIsNone(self.daemon.get_active_client())
        self.api.stop_pipeline()

if __name__ == "__main__":
    unittest.main()
