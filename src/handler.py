import os
import queue
import logging
from typing import Tuple, Set, Optional, Callable
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from src.stability import is_temporary_file

logger = logging.getLogger(__name__)

class AsyncIngestionHandler(FileSystemEventHandler):
    """
    Interprets watchdog file system events, filters out non-temporary directory files,
    temporary/unsupported extensions, and pushes completed file paths to an asynchronous queue.
    Also intercepts trigger signal files (wrap.txt, done.txt, .wrap) for live batch wrap-up.
    """
    def __init__(
        self,
        work_queue: queue.Queue,
        allowed_extensions: Tuple[str, ...] = ('.txt', '.json', '.md', '.csv', '.log', '.pdf'),
        ignored_extensions: Tuple[str, ...] = ('.tmp', '.part', '.crdownload', '.swp', '.lock'),
        wrapup_callback: Optional[Callable[[], None]] = None,
        enqueue_callback: Optional[Callable[[str, str], None]] = None
    ):
        super().__init__()
        self.work_queue = work_queue
        self.allowed_extensions = tuple(ext.lower() for ext in allowed_extensions)
        self.ignored_extensions = tuple(ext.lower() for ext in ignored_extensions)
        self.wrapup_callback = wrapup_callback
        self.enqueue_callback = enqueue_callback

    def _should_process(self, file_path: str) -> bool:
        if not file_path:
            return False
        
        abs_path = os.path.abspath(file_path)

        # Ignore temporary write extensions (~lock, .tmp, etc.)
        if is_temporary_file(abs_path, self.ignored_extensions):
            logger.debug(f"Ignoring temporary or hidden file: {abs_path}")
            return False

        # Check allowed extension
        if not abs_path.lower().endswith(self.allowed_extensions):
            logger.debug(f"File extension not allowed for: {abs_path}")
            return False

        return True

    def _enqueue(self, file_path: str, event_type: str) -> None:
        abs_path = os.path.abspath(file_path)
        file_name = os.path.basename(abs_path).lower()

        # Intercept trigger signal files (wrap.txt, done.txt, .wrap, wrapup.txt)
        if file_name in ('wrap.txt', 'done.txt', '.wrap', 'wrapup.txt', 'wrap'):
            logger.info(f"[TRIGGER SIGNAL] Detected trigger signal file '{file_name}'. Triggering Batch Wrap-Up!")
            try:
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            except Exception as e:
                logger.debug(f"Could not remove trigger file: {e}")

            if self.wrapup_callback:
                self.wrapup_callback()
            return

        if self._should_process(abs_path):
            logger.info(f"{event_type} event detected: {abs_path}")
            self.work_queue.put(abs_path)
            if self.enqueue_callback:
                try:
                    self.enqueue_callback(abs_path, event_type)
                except Exception:
                    pass

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src_path = getattr(event, 'src_path', '')
        self._enqueue(src_path, "Creation")

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        dest_path = getattr(event, 'dest_path', '')
        self._enqueue(dest_path, "Atomic Move/Rename")
