import os
import sys
import time
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

class FileStabilityError(Exception):
    """Raised when a file does not stabilize within the allocated timeout."""
    pass


def is_temporary_file(file_path: str, ignored_extensions: Tuple[str, ...] = ('.tmp', '.part', '.crdownload', '.swp', '.lock')) -> bool:
    """
    Checks if a file path corresponds to a temporary file extension or lock file.
    """
    filename = os.path.basename(file_path).lower()
    return filename.endswith(ignored_extensions) or filename.startswith(('~', '.'))


def check_exclusive_lock(file_path: str) -> bool:
    """
    Attempts to acquire an exclusive lock or non-blocking open on the target file
    to verify that no other process holds an active write handle.
    """
    if not os.path.exists(file_path):
        return False

    if sys.platform == 'win32':
        # On Windows, try opening in read/write mode without sharing write access
        try:
            import msvcrt
            handle = os.open(file_path, os.O_RDWR | os.O_BINARY)
            try:
                # Try locking first byte non-blocking
                msvcrt.locking(handle, msvcrt.LK_NBLCK, 1)
                msvcrt.locking(handle, msvcrt.LK_UNLCK, 1)
                return True
            except (OSError, IOError):
                return False
            finally:
                os.close(handle)
        except (OSError, IOError, ImportError):
            # Fallback to simple read check if exclusive open fails
            try:
                with open(file_path, 'a+b'):
                    pass
                return True
            except (OSError, IOError):
                return False
    else:
        # On Unix-like systems (Linux / macOS), try fcntl flock
        try:
            import fcntl
            with open(file_path, 'a') as f:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    return True
                except (OSError, IOError):
                    return False
        except (ImportError, OSError, IOError):
            return True


def wait_for_file_stability(
    file_path: str,
    timeout: int = 30,
    poll_interval: float = 0.5,
    consecutive_checks: int = 2
) -> bool:
    """
    Polls the file size and access lock until byte count remains constant across 
    consecutive checks and no exclusive lock is held by external processes.
    """
    start_time = time.time()
    last_size = -1
    stable_count = 0

    while time.time() - start_time < timeout:
        if not os.path.exists(file_path):
            time.sleep(poll_interval)
            continue

        try:
            current_size = os.path.getsize(file_path)
            
            # File must exist and have non-zero size (or stable size)
            if current_size >= 0 and current_size == last_size:
                stable_count += 1
                if stable_count >= consecutive_checks:
                    # Also verify exclusive access if possible
                    if check_exclusive_lock(file_path):
                        logger.info(f"File stability confirmed for: {file_path} ({current_size} bytes)")
                        return True
                    else:
                        logger.debug(f"File size stable but exclusive lock unavailable on {file_path}")
            else:
                stable_count = 0
                last_size = current_size

        except OSError as e:
            logger.debug(f"File access restriction on {file_path}: {e}")
            stable_count = 0

        time.sleep(poll_interval)

    raise FileStabilityError(f"Timed out after {timeout}s waiting for file stability: {file_path}")
