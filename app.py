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

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Lumi-nary.ScannedDocumentsRenamer.App.1.0")
    except Exception:
        pass

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
    Internal attributes must start with an underscore to prevent PyWebView reflection recursion.
    """
    def __init__(self, daemon: PipelineDaemon, settings_file: str = "settings.json"):
        self._daemon = daemon
        self._settings_file = settings_file
        self._window: Optional[webview.Window] = None

        # Register event forwarding to webview UI
        self._daemon.add_listener(self._forward_event_to_js)

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    def _forward_event_to_js(self, event: Dict[str, Any]) -> None:
        if self._window:
            try:
                json_payload = json.dumps(event)
                self._window.evaluate_js(f"window.onPipelineEvent({json_payload});")
            except Exception as e:
                logger.debug(f"Could not forward event to JS: {e}")

    def get_initial_data(self) -> Dict[str, Any]:
        """
        Supplies the GUI frontend with initial status, settings, and recent documents.
        """
        return {
            "status": self._daemon.get_status(),
            "settings": self._daemon.config.to_dict(),
            "recent_records": self._daemon.get_recent_records(50)
        }

    def browse_folder(self) -> Optional[str]:
        """
        Opens native Windows folder selection dialog and returns chosen path.
        """
        initial_dir = ""
        if self._daemon.config.watch_directories:
            initial_dir = self._daemon.config.watch_directories[0]
        if not initial_dir or not os.path.exists(initial_dir):
            initial_dir = os.getcwd()

        # 1. Primary: PyWebView native file dialog
        if self._window:
            try:
                result = self._window.create_file_dialog(
                    dialog_type=FileDialog.FOLDER,
                    allow_multiple=False,
                    directory=initial_dir
                )
                if result and len(result) > 0:
                    selected_dir = result[0]
                    logger.info(f"Folder selected via dialog: {selected_dir}")
                    return selected_dir
                # User canceled or closed the dialog: return cleanly without falling through
                return None
            except Exception as e:
                logger.warning(f"pywebview create_file_dialog error: {e}. Falling back to native Windows dialog...")

        # 2. Secondary fallback: Native Windows Forms FolderBrowserDialog (only if pywebview dialog threw an exception or window is absent)
        try:
            escaped_init = initial_dir.replace("'", "''")
            ps_script = (
                "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; "
                "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "$f.Description = 'Select Scanner Output / Watch Folder'; "
                f"$f.SelectedPath = '{escaped_init}'; "
                "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.SelectedPath }"
            )
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=60,
                creationflags=creationflags
            )
            chosen = res.stdout.strip()
            if chosen and os.path.isdir(chosen):
                logger.info(f"Folder selected via native fallback: {chosen}")
                return chosen
        except Exception as e:
            logger.error(f"Fallback folder picker error: {e}")

        return None

    def save_settings(self, settings_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Saves updated settings to settings.json and refreshes daemon configuration.
        """
        try:
            cfg = self._daemon.config
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
            cfg.save(self._settings_file)

            # Update daemon watch directories if running
            self._daemon.update_watch_directories(cfg.watch_directories)
            logger.info("Settings updated and saved successfully.")
            return {"success": True, "settings": cfg.to_dict()}
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return {"success": False, "error": str(e)}

    def start_pipeline(self) -> Dict[str, Any]:
        """
        Starts the background ingestion daemon.
        """
        is_mock = self._daemon.config.provider.lower() == "mock"
        started = self._daemon.start(mock_mode=is_mock)
        return {"success": started, "status": self._daemon.get_status()}

    def stop_pipeline(self) -> Dict[str, Any]:
        """
        Stops the background ingestion daemon.
        """
        stopped = self._daemon.stop()
        return {"success": stopped, "status": self._daemon.get_status()}

    def trigger_wrapup(self) -> List[Dict[str, Any]]:
        """
        Executes immediate batch wrap-up on unprocessed documents.
        """
        return self._daemon.trigger_wrapup()

    def reset_active_client(self) -> None:
        """
        Resets sticky active client context.
        """
        self._daemon.reset_active_client()

    def set_active_client(self, client_name: str) -> None:
        """
        Sets sticky active client context.
        """
        self._daemon.set_active_client(client_name)

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

    icon_candidates = [
        get_asset_path(os.path.join("gui", "icon.ico")),
        os.path.join(os.path.dirname(sys.executable), "icon.ico"),
        os.path.join(os.path.dirname(sys.executable), "_internal", "gui", "icon.ico"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui", "icon.ico")
    ]
    icon_path = next((p for p in icon_candidates if os.path.isfile(p)), None)

    def on_shown():
        if icon_path and sys.platform == "win32":
            try:
                import ctypes
                hwnd = window.native.Handle.ToInt64()
                hbig = ctypes.windll.user32.LoadImageW(0, icon_path, 1, 32, 32, 0x00000010)
                hsmall = ctypes.windll.user32.LoadImageW(0, icon_path, 1, 16, 16, 0x00000010)
                if hbig:
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hbig)
                if hsmall:
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hsmall)
            except Exception as e:
                logger.debug(f"Failed to set window icon via Win32: {e}")

    window.events.shown += on_shown

    try:
        if icon_path:
            webview.start(debug=False, icon=icon_path)
        else:
            webview.start(debug=False)
    finally:
        daemon.stop()


if __name__ == "__main__":
    launch_app()
