"""Local log paths, timestamp formatting and error-only logging policy."""
from __future__ import annotations

import logging
import os
import re
import sys
from datetime import datetime
from typing import Tuple

# Only explicit severity prefixes count as child error messages; INFO/WARN text
# mentioning errors and ordinary stderr progress must stay out of the error file.
ERROR_LINE = re.compile(
    r"^\s*(?:(?:\d+:|\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\s+)*"
    r"(?:TASK\s+)?(?:ERROR|FATAL|CRITICAL)\s*:", re.IGNORECASE,
)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def nonempty_file(path: str) -> bool:
    try:
        return os.path.exists(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def build_log_paths(log_dir: str, prefix: str) -> Tuple[str, str]:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f") + f"-{os.getpid()}"
    logfile = os.path.join(log_dir, f"{prefix}-{ts}.log")
    errfile = os.path.join(log_dir, f"{prefix}-{ts}.err")
    return logfile, errfile


def setup_logger(logfile: str, errfile: str) -> logging.Logger:
    """Send all records to console/full log and ERROR+ records to the error log."""
    logger = logging.getLogger("pbs_backup")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Repeated in-process runs must not retain another run's file destinations.
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)

    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File
    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    eh = logging.FileHandler(errfile, encoding="utf-8", delay=True)
    eh.setLevel(logging.ERROR)
    eh.setFormatter(fmt)
    logger.addHandler(eh)
    return logger


def is_error_line(line: str) -> bool:
    """Recognize Proxmox severity prefixes, not incidental error words in progress."""
    return ERROR_LINE.match(line) is not None
