import os
import sys
import time
import queue
import threading
import logging
from typing import Optional, List, Dict, Any, Callable

from src.config import PipelineConfig
from src.handler import AsyncIngestionHandler
from src.dispatcher import AIAPIDispatcher
from src.watch_manager import DynamicWatchManager
from src.worker import worker_loop
from src.client_manager import ClientManager

logger = logging.getLogger(__name__)

class DaemonLogHandler(logging.Handler):
    """
    Captures log messages and dispatches them to registered UI listeners.
    """
    def __init__(self, dispatch_fn: Callable[[Dict[str, Any]], None]):
        super().__init__()
        self.dispatch_fn = dispatch_fn

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.dispatch_fn({
                "category": "log",
                "level": record.levelname,
                "name": record.name,
                "message": msg,
                "timestamp": time.strftime("%H:%M:%S", time.localtime(record.created))
            })
        except Exception:
            self.handleError(record)

class PipelineDaemon:
    """
    Managed lifecycle controller for the file ingestion and AI classification daemon.
    Thread-safe and decoupled from the presentation layer (CLI or GUI).
    """
    def __init__(self, config: Optional[PipelineConfig] = None, settings_file: str = "settings.json"):
        self.settings_file = settings_file
        self.config = config if config is not None else PipelineConfig.load(settings_file)
        
        self.is_running = False
        self.work_queue: queue.Queue = queue.Queue()
        self.stop_event: threading.Event = threading.Event()
        self.processed_records: List[Dict[str, Any]] = []
        
        self.worker_threads: List[threading.Thread] = []
        self.watch_manager: Optional[DynamicWatchManager] = None
        self.handler: Optional[AsyncIngestionHandler] = None
        self.dispatcher: Optional[AIAPIDispatcher] = None
        self.client_mgr: Optional[ClientManager] = None
        
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._lock = threading.Lock()
        
        # Attach log listener handler
        self._log_handler = DaemonLogHandler(self.emit_event)
        self._log_handler.setFormatter(logging.Formatter("%(message)s"))
        
        root_logger = logging.getLogger()
        if self._log_handler not in root_logger.handlers:
            root_logger.addHandler(self._log_handler)

    def add_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def emit_event(self, event: Dict[str, Any]) -> None:
        with self._lock:
            listeners_snapshot = list(self._listeners)
        for listener in listeners_snapshot:
            try:
                listener(event)
            except Exception as e:
                logger.debug(f"Error in event listener: {e}")

    def get_active_client(self) -> Optional[str]:
        if self.client_mgr:
            return self.client_mgr.get_active_client()
        return None

    def set_active_client(self, client_name: str) -> None:
        if self.client_mgr:
            self.client_mgr.set_active_client(client_name)
            logger.info(f"Set active client context to: '{client_name}'")
            self.emit_status()

    def reset_active_client(self) -> None:
        if self.client_mgr:
            self.client_mgr.reset_active_client()
            logger.info("Reset active client context to None.")
            self.emit_status()

    def get_status(self) -> Dict[str, Any]:
        return {
            "category": "status",
            "is_running": self.is_running,
            "queued_count": self.work_queue.qsize() if self.work_queue else 0,
            "processed_count": len(self.processed_records),
            "active_client": self.get_active_client(),
            "watch_directories": self.config.watch_directories,
            "provider": self.config.provider,
            "model_name": self.config.model_name,
            "enable_wrapup": self.config.enable_wrapup
        }

    def emit_status(self) -> None:
        self.emit_event(self.get_status())

    def get_recent_records(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(reversed(self.processed_records[-limit:]))

    def _on_worker_event(self, event: Dict[str, Any]) -> None:
        payload = {
            "category": "file",
            **event
        }
        self.emit_event(payload)
        self.emit_status()

    def _on_file_enqueued(self, file_path: str, event_type: str) -> None:
        self.emit_event({
            "category": "file",
            "type": "detected",
            "file_path": file_path,
            "filename": os.path.basename(file_path),
            "event_type": event_type,
            "timestamp": time.strftime("%H:%M:%S")
        })
        self.emit_status()

    def trigger_wrapup(self) -> List[Dict[str, Any]]:
        if not self.client_mgr:
            logger.warning("ClientManager not initialized; cannot wrap up batch.")
            return []

        logger.info("Executing Batch Wrap-Up (Creating Client folders & updating Clients.docx)...")
        results = self.client_mgr.wrap_up_batch(self.processed_records)
        self.emit_event({
            "category": "wrapup",
            "results": results,
            "count": len(results),
            "timestamp": time.strftime("%H:%M:%S")
        })
        self.emit_status()
        return results

    def start(self, mock_mode: bool = False) -> bool:
        with self._lock:
            if self.is_running:
                logger.warning("PipelineDaemon is already running.")
                return False

            self.stop_event.clear()
            self.is_running = True

        logger.info("Starting PipelineDaemon...")
        
        # Initialize Client Manager
        base_watch = self.config.watch_directories[0] if self.config.watch_directories else os.getcwd()
        self.client_mgr = ClientManager(
            base_watch_dir=base_watch,
            update_docx=self.config.update_clients_docx
        )

        # Initialize Dispatcher
        is_mock = mock_mode or (self.config.api_key in ("your-api-key-here", "", "YOUR_OPENROUTER_API_KEY_HERE"))
        self.dispatcher = AIAPIDispatcher(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            model_name=self.config.model_name,
            max_retries=self.config.max_retries,
            backoff_factor=self.config.backoff_factor,
            max_backoff_delay=self.config.max_backoff_delay,
            mock_mode=is_mock
        )
        if is_mock:
            logger.info("AI Dispatcher running in MOCK mode (no remote API calls).")
        else:
            logger.info(f"AI Dispatcher active using {self.config.provider.upper()} ({self.config.model_name}).")

        # Initialize Ingestion Handler & Watch Manager
        self.handler = AsyncIngestionHandler(
            work_queue=self.work_queue,
            allowed_extensions=self.config.allowed_extensions,
            ignored_extensions=self.config.ignored_extensions,
            wrapup_callback=self.trigger_wrapup,
            enqueue_callback=self._on_file_enqueued
        )
        self.watch_manager = DynamicWatchManager(event_handler=self.handler)
        self.watch_manager.set_watch_directories(self.config.watch_directories, recursive=True)
        self.watch_manager.start()

        # Enqueue existing files
        for watch_target in self.config.watch_directories:
            if os.path.exists(watch_target):
                for root, _, files in os.walk(watch_target):
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        if self.handler._should_process(fpath):
                            logger.info(f"Enqueuing pre-existing document: {fpath}")
                            self.work_queue.put(fpath)
                            self._on_file_enqueued(fpath, "Existing File")

        # Launch Worker Threads
        self.worker_threads.clear()
        num_workers = max(1, self.config.num_workers)
        for i in range(num_workers):
            t = threading.Thread(
                target=worker_loop,
                args=(
                    self.work_queue,
                    self.dispatcher,
                    self.stop_event,
                    self.config,
                    None,
                    self.processed_records,
                    self.client_mgr,
                    self._on_worker_event
                ),
                name=f"IngestionWorker-{i+1}",
                daemon=True
            )
            t.start()
            self.worker_threads.append(t)

        logger.info(f"Pipeline daemon online with {len(self.worker_threads)} workers. Monitoring: {self.config.watch_directories}")
        self.emit_status()
        return True

    def stop(self, wait_timeout: float = 2.0) -> bool:
        with self._lock:
            if not self.is_running:
                return False
            self.is_running = False
            self.stop_event.set()

        logger.info("Stopping PipelineDaemon...")

        if self.watch_manager:
            try:
                self.watch_manager.stop()
            except Exception as e:
                logger.debug(f"Error stopping watch manager: {e}")

        # Wait briefly for workers to terminate
        for t in self.worker_threads:
            t.join(timeout=wait_timeout)
        self.worker_threads.clear()

        logger.info("PipelineDaemon stopped.")
        self.emit_status()
        return True

    def update_watch_directories(self, directories: List[str]) -> None:
        self.config.watch_directories = directories
        if directories:
            self.config.watch_directory = directories[0]
            if self.client_mgr:
                self.client_mgr.base_directory = directories[0]
        if self.watch_manager and self.is_running:
            self.watch_manager.set_watch_directories(directories, recursive=True)
            logger.info(f"Updated watch directories at runtime: {directories}")
        self.emit_status()
