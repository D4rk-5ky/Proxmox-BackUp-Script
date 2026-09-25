"""Guest selection, vzdump argv construction and streamed subprocess execution."""
from __future__ import annotations

import argparse
import codecs
import json
import logging
import os
import selectors
import shlex
import shutil
import subprocess
import sys
import time
from typing import List, Optional

from .logging_utils import ensure_dir, is_error_line, now_iso


def resolve_selection(args: argparse.Namespace) -> None:
    """Resolve exclusions and optional running-state selection before building argv."""
    excluded = set(args.exclude)
    if not args.all:
        args.vmid = [vmid for vmid in args.vmid if vmid not in excluded]
        if not args.vmid:
            raise ValueError("No selected guests remain after --exclude.")
        args.exclude = []

    if args.only_running:
        # vzdump has no --only-running flag. Query the local node without changing it.
        if shutil.which("pvesh") is None:
            raise ValueError("--only-running requires 'pvesh' on the Proxmox VE node.")
        node = os.uname().nodename.split(".")[0]
        result = subprocess.run(
            ["pvesh", "get", "/cluster/resources", "--type", "vm", "--output-format", "json"],
            check=True, capture_output=True, text=True, timeout=30,
        )
        guests = json.loads(result.stdout)
        if not isinstance(guests, list) or any(not isinstance(guest, dict) for guest in guests):
            raise ValueError("Unexpected pvesh guest inventory; refusing to start backup.")
        running = {str(guest["vmid"]) for guest in guests
                   if guest.get("node") == node and guest.get("status") == "running"
                   and guest.get("type") in ("qemu", "lxc")}
        selected = running - excluded if args.all else set(args.vmid) & running
        if not selected:
            raise ValueError("No running guests match the selection; no backup started.")
        args.vmid = sorted(selected, key=int)
        args.all = False
        args.exclude = []


def build_vzdump_cmd(args: argparse.Namespace) -> List[str]:
    cmd: List[str] = ["vzdump"]

    # Selection
    if args.all:
        cmd.append("--all")
    else:
        # user-provided VMIDs
        cmd += args.vmid
        cmd += ["--all", "0"]

    # Target
    cmd += ["--storage", args.storage]

    # Options
    cmd += ["--mode", args.mode]
    cmd += ["--compress", args.compress]
    cmd += ["--bwlimit", str(args.bwlimit)]

    if args.notes_template:
        cmd += ["--notes-template", args.notes_template]

    if args.exclude:
        cmd += ["--exclude", ",".join(args.exclude)]

    if args.quiet:
        cmd += ["--quiet", "1"]

    # Optional vzdump mail knobs (independent from MQTT)
    if args.mailto:
        cmd += ["--mailto", args.mailto]
    if args.mailnotification:
        cmd += ["--mailnotification", args.mailnotification]

    return cmd


def run_command_stream(
    cmd: List[str],
    logger: logging.Logger,
    logfile: str,
    errfile: str,
    timeout: Optional[int] = None,
    dry_run: bool = False,
) -> int:
    """
    Run a command, stream combined stdout/stderr to terminal in real-time,
    preserve all output in logfile and only error-prefixed lines in errfile.
    The logger from setup_logger also routes wrapper ERROR records to errfile.
    """
    printable = " ".join(shlex.quote(c) for c in cmd)
    logger.info("Running: %s", printable)

    ensure_dir(os.path.dirname(logfile))
    ensure_dir(os.path.dirname(errfile))

    if dry_run:
        logger.info("DRY-RUN: not executing command.")
        return 0

    deadline = None if timeout is None else time.monotonic() + timeout

    with open(logfile, "a", encoding="utf-8") as lf, open(errfile, "a", encoding="utf-8") as ef:
        lf.write(f"[{now_iso()}] Running: {printable}\n")
        lf.flush()

        pending = ""

        def filter_errors(output: str, final: bool = False) -> None:
            """Assemble split lines before filtering; flush a final partial error too."""
            nonlocal pending
            pending += output
            lines = pending.split("\n")
            pending = lines.pop()
            if final and pending:
                lines.append(pending)
                pending = ""
            for line in lines:
                if is_error_line(line):
                    ef.write(line + "\n")
            ef.flush()

        proc = None
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
            assert proc.stdout is not None
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            # Read ready bytes instead of blocking on a newline: silent and partial
            # output must not prevent the deadline from being checked.
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = None if deadline is None else deadline - time.monotonic()
                    if remaining is not None and remaining <= 0:
                        raise TimeoutError(f"Timeout exceeded ({timeout}s)")
                    for key, _ in selector.select(remaining):
                        data = os.read(key.fd, 65536)
                        output = decoder.decode(data, final=not data)
                        sys.stdout.write(output)
                        sys.stdout.flush()
                        lf.write(output)
                        lf.flush()
                        filter_errors(output, final=not data)
                        if not data:
                            selector.unregister(proc.stdout)

            # A child can close stdout before exiting; keep the deadline here too.
            remaining = None if deadline is None else max(0, deadline - time.monotonic())
            rc = proc.wait(timeout=remaining)
            logger.info("Finished (rc=%d)", rc)
            lf.write(f"[{now_iso()}] Finished (rc={rc})\n")
            if rc != 0:
                logger.error("Backup command failed (rc=%d); see full log for details.", rc)
            return rc

        except Exception as e:
            logger.error("FAILED: %s", e)
            return 255
        finally:
            try:
                filter_errors("", final=True)
            finally:
                # Even a final log write failure must not skip subprocess cleanup.
                if proc is not None:
                    if proc.poll() is None:
                        proc.kill()
                    proc.wait()
                    if proc.stdout is not None:
                        proc.stdout.close()
