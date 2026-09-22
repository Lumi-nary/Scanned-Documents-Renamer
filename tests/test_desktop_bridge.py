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

        # Test disable active client context
        res_dis = self.api.set_active_client_enabled(False)
        self.assertTrue(res_dis["success"])
        self.assertFalse(res_dis["active_client_enabled"])
        self.assertFalse(self.daemon.is_active_client_enabled())

        # Test re-enable active client context
        res_en = self.api.set_active_client_enabled(True)
        self.assertTrue(res_en["success"])
        self.assertTrue(res_en["active_client_enabled"])
        self.assertTrue(self.daemon.is_active_client_enabled())

        self.api.stop_pipeline()

    def test_save_settings_with_new_folder_and_scan(self):
        new_watch = os.path.join(self.temp_dir, "SubWatch", "Batch1")
        os.makedirs(new_watch, exist_ok=True)
        pdf_file = os.path.join(new_watch, "doc.pdf")
        with open(pdf_file, "w") as f:
            f.write("%PDF-1.4 sample")

        clients_root = os.path.join(self.temp_dir, "Clients")
        os.makedirs(os.path.join(clients_root, "Litigation", "Client A"), exist_ok=True)

        self.api.start_pipeline()
        res = self.api.save_settings({
            "watch_directories": [new_watch],
            "clients_directory": clients_root,
            "provider": "mock"
        })
        self.assertTrue(res["success"])
        self.assertIn("enqueued_count", res)
        self.assertEqual(res["enqueued_count"], 1)
        self.assertIn("Client A", res["client_list"])

        # Test scan_client_directories with custom directory
        custom_scan = self.api.scan_client_directories(custom_dir=clients_root)
        self.assertTrue(custom_scan["success"])
        self.assertIn("Client A", custom_scan["clients"])

        self.api.stop_pipeline()

    def test_bridge_instructions(self):
        # 1. get_initial_data should include instructions
        init_data = self.api.get_initial_data()
        self.assertIn("instructions", init_data)
        self.assertIn("prompt_preview", init_data)

        # 2. get_instructions
        res = self.api.get_instructions()
        self.assertTrue(res["success"])
        self.assertIn("instructions", res)
        self.assertIn("prompt_preview", res)

        # 3. save_instructions with new custom rule
        file_types = res["instructions"]["file_types"]
        custom_rule = {
            "id": "po_rule",
            "name": "Purchase Order",
            "is_preset": False,
            "enabled": True,
            "priority": 1,
            "match_keywords": ["Purchase Order", "PO#"],
            "naming_format": "Purchase Order <PO_NUM>.pdf",
            "instructions": "Extract PO Number."
        }
        updated_types = [custom_rule] + file_types
        save_res = self.api.save_instructions({"file_types": updated_types})
        self.assertTrue(save_res["success"])
        self.assertEqual(len(save_res["instructions"]["file_types"]), len(file_types) + 1)
        self.assertIn("Purchase Order", save_res["prompt_preview"])

        # 4. reset_instructions
        reset_res = self.api.reset_instructions()
        self.assertTrue(reset_res["success"])
        self.assertEqual(len(reset_res["instructions"]["file_types"]), len(file_types))

if __name__ == "__main__":
    unittest.main()

