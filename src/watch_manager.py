import os
import threading
import logging
from typing import Optional, List, Dict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

class DynamicWatchManager:
    """
    Manages the Watchdog Observer state and provides dynamic runtime updating 
    and multi-directory monitoring (including folders outside the project root).
    """
    def __init__(self, event_handler: FileSystemEventHandler):
        self.observer = Observer()
        self.event_handler = event_handler
        self.current_watches: Dict[str, any] = {}
        self._lock = threading.Lock()

    def start(self) -> None:
        """Starts the observer daemon thread."""
        with self._lock:
            if not self.observer.is_alive():
                self.observer.start()
                logger.info("Watchdog Observer thread started.")

    def stop(self) -> None:
        """Stops the observer daemon thread and waits for join."""
        with self._lock:
            if self.observer.is_alive():
                self.observer.stop()
                self.observer.join()
                logger.info("Watchdog Observer thread stopped.")

    def add_watch_directory(self, new_directory_path: str, recursive: bool = True) -> str:
        """
        Adds a new target directory to monitor (external or internal path).
        """
        with self._lock:
            abs_path = os.path.abspath(new_directory_path)
            if abs_path in self.current_watches:
                logger.info(f"Directory already being monitored: {abs_path}")
                return abs_path

            if not os.path.exists(abs_path):
                os.makedirs(abs_path, exist_ok=True)
                logger.info(f"Created target directory: {abs_path}")

            watch_handle = self.observer.schedule(
                self.event_handler, abs_path, recursive=recursive
            )
            self.current_watches[abs_path] = watch_handle
            logger.info(f"Successfully added watch target: {abs_path} (recursive={recursive})")
            return abs_path

    def set_watch_directory(self, new_directory_path: str, recursive: bool = True) -> str:
        """
        Sets a single watch directory path (backwards-compatibility wrapper).
        """
        res = self.set_watch_directories([new_directory_path], recursive=recursive)
        return res[0] if res else os.path.abspath(new_directory_path)

    def set_watch_directories(self, directory_paths: List[str], recursive: bool = True) -> List[str]:
        """
        Replaces current watched directory targets with a new list of directory paths.
        """
        with self._lock:
            # Unschedule existing handles
            for abs_path, watch_handle in list(self.current_watches.items()):
                self.observer.unschedule(watch_handle)
            self.current_watches.clear()

            added_paths = []
            for path in directory_paths:
                abs_path = os.path.abspath(path)
                if not os.path.exists(abs_path):
                    os.makedirs(abs_path, exist_ok=True)
                    logger.info(f"Created target directory: {abs_path}")

                watch_handle = self.observer.schedule(
                    self.event_handler, abs_path, recursive=recursive
                )
                self.current_watches[abs_path] = watch_handle
                added_paths.append(abs_path)
                logger.info(f"Monitoring watch directory: {abs_path} (recursive={recursive})")

            return added_paths

    def get_current_directory(self) -> Optional[str]:
        """Returns the primary monitored directory path."""
        with self._lock:
            if self.current_watches:
                return list(self.current_watches.keys())[0]
            return None

    def get_monitored_directories(self) -> List[str]:
        """Returns list of all currently active monitored directory paths."""
        with self._lock:
            return list(self.current_watches.keys())
