import os
import sys
import time
import queue
import signal
import threading
import logging
import argparse
from typing import List

from src.config import PipelineConfig, PROVIDER_PRESETS
from src.handler import AsyncIngestionHandler
from src.dispatcher import AIAPIDispatcher
from src.watch_manager import DynamicWatchManager
from src.worker import worker_loop
from src.batch import BatchManifestBuilder
from src.client_manager import ClientManager

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(threadName)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

def main():
    parser = argparse.ArgumentParser(description="Automated File-Driven AI Ingestion Pipeline")
    parser.add_argument("--watch-dir", type=str, default=None, help="Add custom target directory to watch")
    parser.add_argument("--output-dir", type=str, default=None, help="Directory to save AI response files")
    parser.add_argument("--provider", type=str, choices=list(PROVIDER_PRESETS.keys()), default=None, help="AI Provider preset")
    parser.add_argument("--mock", action="store_true", help="Run in mock API mode without network calls")
    parser.add_argument("--workers", type=int, default=2, help="Number of worker threads")
    parser.add_argument("--batch-export", type=str, default=None, help="Export queued files to a JSONL batch API manifest and exit")
    parser.add_argument("--wrap-batch", action="store_true", help="Force wrap up batch on exit/completion (creates Client folders and updates Clients.docx)")
    parser.add_argument("--enable-wrapup", action="store_true", help="Enable automatic batch wrapup functions")
    parser.add_argument("--disable-wrapup", action="store_true", help="Disable batch wrapup functions")
    parser.add_argument("--wrap", action="store_true", help="Signal active running pipeline daemon to wrap up current batch immediately")
    parser.add_argument("--demo", action="store_true", help="Run runtime path swapping demonstration")
    parser.add_argument("--gui", action="store_true", help="Launch the PyWebView Desktop GUI")
    args = parser.parse_args()

    if args.gui:
        from app import launch_app
        launch_app()
        return

    setup_logging()
    logger = logging.getLogger("MainPipeline")

    config = PipelineConfig.load("settings.json")

    if args.enable_wrapup:
        config.enable_wrapup = True
    if args.disable_wrapup:
        config.enable_wrapup = False

    # If --wrap signal flag is invoked, drop .wrap signal file in watched directory and parent Temporary directory
    if args.wrap:
        target_dirs = config.watch_directories if config.watch_directories else [os.getcwd()]
        for target_dir in target_dirs:
            signal_file = os.path.join(target_dir, ".wrap")
            parent_signal = os.path.join(os.path.dirname(target_dir), ".wrap")
            for s_path in (signal_file, parent_signal):
                try:
                    os.makedirs(os.path.dirname(s_path), exist_ok=True)
                    with open(s_path, "w", encoding="utf-8") as f:
                        f.write("wrapup_signal")
                except Exception:
                    pass
            logger.info(f"Sent batch wrap-up signal to running daemon in '{target_dir}'. Exiting CLI.")
        return

    if args.provider:
        config.apply_provider_preset(args.provider)
    if args.watch_dir:
        config.watch_directories.append(os.path.abspath(args.watch_dir))
    if args.workers:
        config.num_workers = args.workers

    logger.info(f"Using Provider: {config.provider.upper()} | Endpoint: {config.base_url} | Model: {config.model_name}")
    logger.info(f"Batch Wrap-Up Functions Status: {'ENABLED' if config.enable_wrapup else 'DISABLED'}")

    if args.batch_export:
        logger.info("Generating batch API manifest from watched directories...")
        builder = BatchManifestBuilder(model_name=config.model_name)
        for watch_dir in config.watch_directories:
            if os.path.exists(watch_dir):
                for root, dirs, files in os.walk(watch_dir):
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        if fname.endswith(config.allowed_extensions):
                            builder.add_file(fpath)
        builder.export_jsonl(args.batch_export)
        return

    work_queue = queue.Queue()
    stop_event = threading.Event()
    processed_records = []

    client_mgr = ClientManager(
        config.watch_directories[0] if config.watch_directories else os.getcwd(),
        update_docx=config.update_clients_docx
    )

    def perform_batch_wrapup():
        if not config.enable_wrapup and not args.wrap_batch:
            logger.info("Batch Wrap-Up functions are disabled. Skipping client folder creation and Clients.docx updates.")
            return

        logger.info("Executing Batch Wrap-Up (Creating Client folders & updating Clients.docx)...")
        results = client_mgr.wrap_up_batch(processed_records)
        if not results:
            logger.info("No files were found or moved during Batch Wrap-Up.")
        else:
            for res in results:
                logger.info(f"[Batch Wrap-Up] Client: '{res['client_name']}' | Date Range: '{res['date_range']}' | Folder: '{res['client_dir']}' | Files: {len(res['moved_files'])}")

    logger.info("Initializing AI API Dispatcher...")
    dispatcher = AIAPIDispatcher(
        api_key=config.api_key,
        base_url=config.base_url,
        model_name=config.model_name,
        max_retries=config.max_retries,
        backoff_factor=config.backoff_factor,
        max_backoff_delay=config.max_backoff_delay,
        mock_mode=args.mock or (config.api_key == "your-api-key-here")
    )

    logger.info("Initializing Watchdog Event Handler & Dynamic Watch Manager...")
    handler = AsyncIngestionHandler(
        work_queue=work_queue,
        allowed_extensions=config.allowed_extensions,
        ignored_extensions=config.ignored_extensions,
        wrapup_callback=perform_batch_wrapup
    )
    watch_manager = DynamicWatchManager(event_handler=handler)

    monitored_paths = watch_manager.set_watch_directories(config.watch_directories, recursive=True)
    watch_manager.start()

    # Enqueue pre-existing files in monitored directories on startup
    for watch_target in config.watch_directories:
        if os.path.exists(watch_target):
            for root, _, files in os.walk(watch_target):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    if handler._should_process(fpath):
                        logger.info(f"Enqueuing pre-existing file on startup: {fpath}")
                        work_queue.put(fpath)

    logger.info(f"Starting background worker pool ({config.num_workers} threads)...")
    worker_threads: List[threading.Thread] = []
    for i in range(config.num_workers):
        t = threading.Thread(
            target=worker_loop,
            args=(work_queue, dispatcher, stop_event, config, args.output_dir, processed_records, client_mgr),
            name=f"IngestionWorker-{i+1}",
            daemon=True
        )
        t.start()
        worker_threads.append(t)

    # Interactive console command listener thread
    def console_listener():
        logger.info("Live console active: Commands: 'client' (view active client), 'reset' (clear active client), 'status'")
        while not stop_event.is_set():
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                cmd = line.strip().lower()
                if cmd in ('client', 'c'):
                    logger.info(f"[Active Client] Current sticky client context: '{client_mgr.get_active_client()}'")
                elif cmd in ('reset', 'clear', 'reset-client', 'clear-client'):
                    client_mgr.reset_active_client()
                    logger.info("[Active Client] Sticky client context reset to None.")
                elif cmd == 'status':
                    logger.info(f"[Status] Queued: {work_queue.qsize()} | Active Client: '{client_mgr.get_active_client()}' | Processed files: {len(processed_records)}")
                elif cmd in ('wrap', 'wrapup', 'w', 'done'):
                    logger.info(f"[Console Command] '{cmd}' received. Checking for any unrouted files...")
                    perform_batch_wrapup()
            except Exception:
                break

    c_thread = threading.Thread(target=console_listener, name="ConsoleListener", daemon=True)
    c_thread.start()

    def shutdown_handler(signum, frame):
        logger.info("Shutdown signal received. Initiating graceful shutdown...")
        stop_event.set()
        watch_manager.stop()
        work_queue.join()
        perform_batch_wrapup()
        logger.info("Pipeline gracefully shutdown.")
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)
    except (ValueError, AttributeError):
        pass

    logger.info(f"Pipeline daemon active. Currently monitoring ({len(monitored_paths)} targets): {monitored_paths}")

    if args.demo:
        logger.info("--- Starting runtime path migration demo ---")
        time.sleep(3)
        new_demo_path = os.path.join(os.getcwd(), "FolderName2", "Temporary")
        logger.info(f"Switching watch directory target at runtime to: {new_demo_path}")
        watch_manager.set_watch_directories([new_demo_path], recursive=True)
        time.sleep(3)
        logger.info("Demo complete. Exiting...")
        stop_event.set()
        watch_manager.stop()
        work_queue.join()
        logger.info("Demo finished successfully.")
        return

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Shutting down...")
        stop_event.set()
        watch_manager.stop()
        work_queue.join()
        logger.info("Pipeline terminated.")

if __name__ == "__main__":
    main()
