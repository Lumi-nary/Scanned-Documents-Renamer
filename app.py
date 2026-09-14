import os
import sys
import json
import logging
import subprocess
from typing import Optional, Dict, Any, List

import webview
from webview import FileDialog

from src.config import PipelineConfig
from src.pipeline_daemon import PipelineDaemon

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AppGUI")

class DesktopBridgeAPI:
    """
    Python API bridge exposed directly to the PyWebView JavaScript runtime.
    Methods defined here are callable from JavaScript via `window.pywebview.api.<method>()`.
    """
    def __init__(self, daemon: PipelineDaemon, settings_file: str = "settings.json"):
        self.daemon = daemon
        self.settings_file = settings_file
        self.window: Optional[webview.Window] = None

        # Register event forwarding to webview UI
        self.daemon.add_listener(self._forward_event_to_js)

    def set_window(self, window: webview.Window) -> None:
        self.window = window

    def _forward_event_to_js(self, event: Dict[str, Any]) -> None:
        if self.window:
            try:
                json_payload = json.dumps(event)
                self.window.evaluate_js(f"window.onPipelineEvent({json_payload});")
            except Exception as e:
                logger.debug(f"Could not forward event to JS: {e}")

    def get_initial_data(self) -> Dict[str, Any]:
        """
        Supplies the GUI frontend with initial status, settings, and recent documents.
        """
        return {
            "status": self.daemon.get_status(),
            "settings": self.daemon.config.to_dict(),
            "recent_records": self.daemon.get_recent_records(50)
        }

    def browse_folder(self) -> Optional[str]:
        """
        Opens native Windows folder selection dialog and returns chosen path.
        """
        if not self.window:
            return None
        
        try:
            result = self.window.create_file_dialog(
                dialog_type=FileDialog.FOLDER,
                allow_multiple=False,
                directory=self.daemon.config.watch_directories[0] if self.daemon.config.watch_directories else os.getcwd()
            )
            if result and len(result) > 0:
                selected_dir = result[0]
                logger.info(f"Folder selected via dialog: {selected_dir}")
                return selected_dir
        except Exception as e:
            logger.error(f"Error opening folder picker dialog: {e}")
        return None

    def save_settings(self, settings_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Saves updated settings to settings.json and refreshes daemon configuration.
        """
        try:
            cfg = self.daemon.config
            if "watch_directories" in settings_dict:
                cfg.watch_directories = [os.path.abspath(p) for p in settings_dict["watch_directories"] if p]
                if cfg.watch_directories:
                    cfg.watch_directory = cfg.watch_directories[0]
            if "provider" in settings_dict:
                cfg.provider = settings_dict["provider"]
                if cfg.provider != "mock":
                    cfg.apply_provider_preset(cfg.provider)
            if "model_name" in settings_dict and settings_dict["model_name"]:
                cfg.model_name = settings_dict["model_name"]
            if "api_key" in settings_dict:
                cfg.api_key = settings_dict["api_key"]
            if "num_workers" in settings_dict:
                cfg.num_workers = int(settings_dict["num_workers"])
            if "stability_timeout" in settings_dict:
                cfg.stability_timeout = int(settings_dict["stability_timeout"])
            if "enable_wrapup" in settings_dict:
                cfg.enable_wrapup = bool(settings_dict["enable_wrapup"])
            if "update_clients_docx" in settings_dict:
                cfg.update_clients_docx = bool(settings_dict["update_clients_docx"])

            # Persist to settings.json
            cfg.save(self.settings_file)

            # Update daemon watch directories if running
            self.daemon.update_watch_directories(cfg.watch_directories)
            logger.info("Settings updated and saved successfully.")
            return {"success": True, "settings": cfg.to_dict()}
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return {"success": False, "error": str(e)}

    def start_pipeline(self) -> Dict[str, Any]:
        """
        Starts the background ingestion daemon.
        """
        is_mock = self.daemon.config.provider.lower() == "mock"
        started = self.daemon.start(mock_mode=is_mock)
        return {"success": started, "status": self.daemon.get_status()}

    def stop_pipeline(self) -> Dict[str, Any]:
        """
        Stops the background ingestion daemon.
        """
        stopped = self.daemon.stop()
        return {"success": stopped, "status": self.daemon.get_status()}

    def trigger_wrapup(self) -> List[Dict[str, Any]]:
        """
        Executes immediate batch wrap-up on unprocessed documents.
        """
        return self.daemon.trigger_wrapup()

    def reset_active_client(self) -> None:
        """
        Resets sticky active client context.
        """
        self.daemon.reset_active_client()

    def set_active_client(self, client_name: str) -> None:
        """
        Sets sticky active client context.
        """
        self.daemon.set_active_client(client_name)

    def reveal_in_explorer(self, target_path: str) -> None:
        """
        Opens Windows Explorer with the target file or folder selected.
        """
        if not target_path:
            return

        try:
            norm_path = os.path.normpath(os.path.abspath(target_path))
            if os.path.isfile(norm_path):
                subprocess.Popen(["explorer", f"/select,{norm_path}"])
            elif os.path.isdir(norm_path):
                os.startfile(norm_path)
            else:
                parent = os.path.dirname(norm_path)
                if os.path.exists(parent):
                    os.startfile(parent)
        except Exception as e:
            logger.error(f"Error opening Windows Explorer for '{target_path}': {e}")


def get_asset_path(relative_path: str) -> str:
    """
    Returns absolute path to an asset, handling both development and PyInstaller frozen states.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base_path, relative_path))


def get_user_config_path() -> str:
    """
    Determines persistent location for settings.json.
    Prefers executable directory (portable mode), falls back to AppData if installed in read-only folder.
    """
    if not getattr(sys, "frozen", False):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "settings.json")

    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    exe_settings = os.path.join(exe_dir, "settings.json")

    # If settings.json already exists next to executable, use it
    if os.path.exists(exe_settings):
        return exe_settings

    # Test if exe directory is writable (e.g. portable zip unpack)
    try:
        test_file = os.path.join(exe_dir, ".write_test")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        return exe_settings
    except (PermissionError, OSError):
        # Installed in Program Files -> persist in %LOCALAPPDATA%
        appdata_dir = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "ScannedDocumentsRenamer"
        )
        os.makedirs(appdata_dir, exist_ok=True)
        return os.path.join(appdata_dir, "settings.json")


def launch_app():
    """
    Initializes configuration, daemon, and launches the native PyWebView window.
    """
    html_file = get_asset_path(os.path.join("gui", "index.html"))

    if not os.path.exists(html_file):
        logger.error(f"Could not find UI entry file at: {html_file}")
        sys.exit(1)

    settings_file = get_user_config_path()
    if not os.path.exists(settings_file):
        example_settings = get_asset_path("settings.example.json")
        if os.path.exists(example_settings):
            import shutil
            os.makedirs(os.path.dirname(settings_file), exist_ok=True)
            shutil.copyfile(example_settings, settings_file)
            logger.info(f"Created settings.json from template at {settings_file}")

    config = PipelineConfig.load(settings_file)
    daemon = PipelineDaemon(config=config, settings_file=settings_file)
    api = DesktopBridgeAPI(daemon=daemon, settings_file=settings_file)

    logger.info("Initializing PyWebView Desktop Window...")
    window = webview.create_window(
        title="Scanned Documents Renamer",
        url=html_file,
        js_api=api,
        width=1120,
        height=760,
        min_size=(920, 620),
        background_color="#080c14"
    )
    api.set_window(window)

    def on_closed():
        logger.info("Desktop window closing. Shutting down daemon...")
        daemon.stop()

    window.events.closed += on_closed

    icon_path = get_asset_path(os.path.join("gui", "icon.ico"))
    if not os.path.exists(icon_path):
        icon_path = get_asset_path(os.path.join("gui", "icon.png"))

    try:
        if os.path.exists(icon_path):
            webview.start(debug=False, icon=icon_path)
        else:
            webview.start(debug=False)
    finally:
        daemon.stop()


if __name__ == "__main__":
    launch_app()
