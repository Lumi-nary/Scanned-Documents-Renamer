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
        
        # Initialize Client Manager immediately so client selection works before daemon start
        base_watch = self.config.watch_directories[0] if self.config.watch_directories else os.getcwd()
        self.client_mgr: ClientManager = ClientManager(
            base_watch_dir=base_watch,
            clients_dir=self.config.clients_directory,
            update_docx=self.config.update_clients_docx
        )
        
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

    def _ensure_client_mgr(self) -> ClientManager:
        if self.client_mgr is None:
            base_watch = self.config.watch_directories[0] if self.config.watch_directories else os.getcwd()
            self.client_mgr = ClientManager(
                base_watch_dir=base_watch,
                clients_dir=self.config.clients_directory,
                update_docx=self.config.update_clients_docx
            )
        return self.client_mgr

    def get_active_client(self) -> Optional[str]:
        return self._ensure_client_mgr().get_active_client()

    def set_active_client(self, client_name: str) -> None:
        self._ensure_client_mgr().set_active_client(client_name)
        logger.info(f"Set active client context to: '{client_name}'")
        self.emit_status()

    def is_client_locked(self) -> bool:
        return self._ensure_client_mgr().is_locked()

    def set_client_locked(self, locked: bool) -> None:
        self._ensure_client_mgr().set_client_locked(locked)
        logger.info(f"Set active client lock state to: {locked}")
        self.emit_status()

    def set_and_lock_client(self, client_name: Optional[str], locked: bool = True) -> None:
        self._ensure_client_mgr().set_and_lock_client(client_name, locked)
        logger.info(f"Set and locked active client to: '{self.get_active_client()}' (locked={locked})")
        self.emit_status()

    def lock_active_client(self, client_name: Optional[str] = None) -> None:
        self._ensure_client_mgr().lock_active_client(client_name)
        logger.info(f"Locked active client to: '{self.get_active_client()}'")
        self.emit_status()

    def unlock_active_client(self) -> None:
        self._ensure_client_mgr().unlock_active_client()
        logger.info("Unlocked active client context.")
        self.emit_status()

    def reset_active_client(self) -> None:
        self._ensure_client_mgr().reset_active_client()
        logger.info("Reset active client context to None (unlocked).")
        self.emit_status()

    def get_status(self) -> Dict[str, Any]:
        return {
            "category": "status",
            "is_running": self.is_running,
            "queued_count": self.work_queue.qsize() if self.work_queue else 0,
            "processed_count": len(self.processed_records),
            "active_client": self.get_active_client(),
            "is_client_locked": self.is_client_locked(),
            "watch_directories": self.config.watch_directories,
            "clients_directory": self.config.clients_directory,
            "provider": self.config.provider,
            "model_name": self.config.model_name,
            "enable_wrapup": self.config.enable_wrapup
        }

    def emit_status(self) -> None:
        self.emit_event(self.get_status())

    def get_recent_records(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(reversed(self.processed_records[-limit:]))

    def get_client_directories(self, custom_root: Optional[str] = None) -> List[str]:
        if self.client_mgr:
            return self.client_mgr.get_client_directories(custom_root=custom_root)
        base_watch = self.config.watch_directories[0] if self.config.watch_directories else os.getcwd()
        from src.client_manager import ClientManager
        cm = ClientManager(base_watch_dir=base_watch, clients_dir=self.config.clients_directory)
        return cm.get_client_directories(custom_root=custom_root)

    def update_record_file(self, old_path: str, new_path: str, new_filename: str) -> None:
        norm_old = os.path.normpath(os.path.abspath(old_path))
        with self._lock:
            for r in self.processed_records:
                r_dest = os.path.normpath(os.path.abspath(r.get("dest_path") or r.get("file_path") or ""))
                if r_dest == norm_old:
                    r["dest_path"] = new_path
                    r["file_path"] = new_path
                    r["dest_filename"] = new_filename
                    r["filename"] = new_filename

    def update_record_client(self, old_path: str, new_path: str, new_client: str) -> None:
        norm_old = os.path.normpath(os.path.abspath(old_path))
        with self._lock:
            for r in self.processed_records:
                r_dest = os.path.normpath(os.path.abspath(r.get("dest_path") or r.get("file_path") or ""))
                if r_dest == norm_old:
                    r["dest_path"] = new_path
                    r["file_path"] = new_path
                    r["client_name"] = new_client

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
        
        # Preserve existing Client Manager state if already initialized
        base_watch = self.config.watch_directories[0] if self.config.watch_directories else os.getcwd()
        if self.client_mgr is None:
            self.client_mgr = ClientManager(
                base_watch_dir=base_watch,
                clients_dir=self.config.clients_directory,
                update_docx=self.config.update_clients_docx
            )
        else:
            self.client_mgr.set_base_directory(base_watch, clients_dir=self.config.clients_directory)
            self.client_mgr.update_docx = self.config.update_clients_docx

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

        # Enqueue existing files (recursively scanning all watch directories and subfolders)
        enqueued = self.scan_and_enqueue_existing(self.config.watch_directories, source_label="Existing File")
        logger.info(f"Initial scan enqueued {len(enqueued)} pre-existing document(s).")

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

    def scan_and_enqueue_existing(
        self,
        directories: Optional[List[str]] = None,
        source_label: str = "Existing File"
    ) -> List[str]:
        """
        Recursively scans target watch directories and all nested subfolders,
        skipping temporary files, hidden directories, build artifacts, and client destination folders,
        and enqueues eligible document files into the work queue.
        Returns the list of newly enqueued file paths.
        """
        targets = directories if directories is not None else self.config.watch_directories
        if not targets:
            return []

        enqueued = []
        ignored_dir_names = {
            ".git", ".idea", ".vscode", "output", "build", "dist",
            "__pycache__", "gui", "tests", "src", "installer"
        }

        # Resolve destination clients directory path to avoid re-scanning already organized files
        client_dest_root = None
        if self.config.clients_directory and os.path.exists(self.config.clients_directory):
            client_dest_root = os.path.normcase(os.path.abspath(self.config.clients_directory))
        elif self.client_mgr and self.client_mgr.root_dir and os.path.exists(self.client_mgr.root_dir):
            client_dest_root = os.path.normcase(os.path.abspath(self.client_mgr.root_dir))

        # Collect currently queued files to avoid re-enqueuing duplicates
        currently_queued = set()
        if self.work_queue:
            with self.work_queue.mutex:
                currently_queued = {os.path.normcase(os.path.abspath(p)) for p in self.work_queue.queue}

        already_processed = set()
        with self._lock:
            for r in self.processed_records:
                src_p = r.get("file_path") or ""
                dst_p = r.get("dest_path") or ""
                if src_p:
                    already_processed.add(os.path.normcase(os.path.abspath(src_p)))
                if dst_p:
                    already_processed.add(os.path.normcase(os.path.abspath(dst_p)))

        for watch_target in targets:
            abs_target = os.path.abspath(watch_target)
            if not os.path.exists(abs_target):
                continue

            for root, dirs, files in os.walk(abs_target):
                # Filter out system and ignored directories in-place
                dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() not in ignored_dir_names]

                # If the watch directory encompasses the client destination root,
                # do not descend into client folders that are already organized!
                if client_dest_root:
                    norm_root = os.path.normcase(os.path.abspath(root))
                    if norm_root == client_dest_root:
                        # Only keep staging subdirectories like Temporary, Unprocessed
                        dirs[:] = [d for d in dirs if d.lower() in ("temporary", "temp", "unproccesed", "unprocessed")]

                for fname in sorted(files):
                    if fname.startswith(('~', '.')):
                        continue
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in self.config.allowed_extensions or ext in self.config.ignored_extensions:
                        continue

                    fpath = os.path.join(root, fname)
                    norm_fpath = os.path.normcase(os.path.abspath(fpath))

                    if norm_fpath in currently_queued or norm_fpath in already_processed:
                        continue

                    # Check file eligibility
                    should_process = True
                    if self.handler:
                        should_process = self.handler._should_process(fpath)
                    else:
                        from src.stability import is_temporary_file
                        should_process = not is_temporary_file(fpath, self.config.ignored_extensions)

                    if should_process and os.path.isfile(fpath):
                        if self.work_queue:
                            self.work_queue.put(fpath)
                            currently_queued.add(norm_fpath)
                            self._on_file_enqueued(fpath, source_label)
                            enqueued.append(fpath)
                            logger.info(f"Enqueued document from watch target ({source_label}): {fpath}")

        return enqueued

    def update_watch_directories(self, directories: List[str]) -> List[str]:
        self.config.watch_directories = directories
        if directories:
            self.config.watch_directory = directories[0]
            if self.client_mgr:
                self.client_mgr.set_base_directory(directories[0], clients_dir=self.config.clients_directory)
        enqueued = []
        if self.watch_manager and self.is_running:
            self.watch_manager.set_watch_directories(directories, recursive=True)
            logger.info(f"Updated watch directories at runtime: {directories}")
            # Scan new folders for existing files immediately upon settings update
            enqueued = self.scan_and_enqueue_existing(directories, source_label="Settings Change Scan")
            logger.info(f"Settings change scan enqueued {len(enqueued)} document(s).")
        self.emit_status()
        return enqueued

    def update_clients_directory(self, clients_dir: Optional[str]) -> List[str]:
        clean_dir = os.path.abspath(clients_dir.strip()) if clients_dir and clients_dir.strip() else None
        self.config.clients_directory = clean_dir
        if self.client_mgr:
            base_watch = self.config.watch_directories[0] if self.config.watch_directories else os.getcwd()
            self.client_mgr.set_base_directory(base_watch, clients_dir=clean_dir)
            logger.info(f"Updated clients directory at runtime: {clean_dir}")
        self.emit_status()
        return self.get_client_directories()

    def scan_watched_folder(self) -> List[str]:
        """
        Manually scans all watched directories (recursively including subfolders)
        and enqueues eligible document files.
        """
        enqueued = self.scan_and_enqueue_existing(self.config.watch_directories, source_label="Manual Scan")
        logger.info(f"Manual scan enqueued {len(enqueued)} document(s).")
        self.emit_status()
        return enqueued
