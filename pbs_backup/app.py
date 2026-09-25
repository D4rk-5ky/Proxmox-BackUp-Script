"""Application lifecycle: preflight, backup/preview and notification outcomes."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

from . import notifications
from .backup import build_vzdump_cmd, resolve_selection, run_command_stream
from .cli import parse_args
from .logging_utils import build_log_paths, ensure_dir, nonempty_file, setup_logger


def is_root() -> bool:
    return os.geteuid() == 0


def main() -> int:
    args = parse_args()

    try:
        ensure_dir(args.log_dir)
        logfile, errfile = build_log_paths(args.log_dir, args.log_prefix)
        logger = setup_logger(logfile, errfile)
    except OSError as e:
        print(f"ERROR: Cannot initialize logs: {e}", file=sys.stderr)
        return 2

    if not is_root():
        logger.error("Must run as root (sudo) because vzdump needs privileges.")
        return 2

    if shutil.which("vzdump") is None:
        logger.error("'vzdump' not found. Run on a Proxmox VE node.")
        return 2

    if notifications.mqtt is None:
        logger.error("paho-mqtt not installed. Install with: pip install paho-mqtt")
        return 2

    try:
        resolve_selection(args)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as e:
        logger.error("Guest selection failed: %s", e)
        return 2

    node = os.uname().nodename
    client_id = args.mqtt_client_id or f"proxmox-backup-{node}"

    cmd = build_vzdump_cmd(args)

    logger.info("Node=%s Storage=%s Topic=%s", node, args.storage, args.mqtt_topic)

    start_ts = time.monotonic()
    rc = run_command_stream(
        cmd,
        logger=logger,
        logfile=logfile,
        errfile=errfile,
        timeout=args.timeout,
        dry_run=args.dry_run,
    )
    duration_s = int(time.monotonic() - start_ts)

    mqtt_result = "disabled"
    email_result = "disabled"
    if args.dry_run and args.dry_run_email:
        try:
            notifications.send_dry_run_email(
                mailto=args.mailto, node=node, storage=args.storage, cmd=cmd,
                log_file=logfile, err_file=errfile, logger=logger,
            )
            email_result = "submitted"
        except Exception as e:
            email_result = "failed"
            logger.error("Dry-run email failed: %s", e)

    # Each requested channel is attempted independently; never publish backup success for a preview.
    if not args.dry_run or args.dry_run_mqtt:
        try:
            notifications.publish_backup_status(
                rc=rc,
                duration_s=duration_s,
                node=node,
                storage=args.storage,
                log_file=logfile,
                err_file=errfile,
                mqtt_host=args.mqtt_host,
                mqtt_port=args.mqtt_port,
                mqtt_topic=args.mqtt_topic,
                mqtt_user=args.mqtt_user,
                mqtt_pass=args.mqtt_pass,
                mqtt_tls=args.mqtt_tls,
                mqtt_cafile=args.mqtt_cafile,
                mqtt_insecure=args.mqtt_insecure,
                mqtt_client_id=client_id,
                mqtt_retain=args.mqtt_retain,
                mqtt_qos=args.mqtt_qos,
                mqtt_timeout=args.mqtt_timeout,
                logger=logger,
                dry_run=args.dry_run,
            )
            mqtt_result = "published"
        except Exception as e:
            mqtt_result = "failed"
            logger.error("MQTT publish failed: %s", e)


    if args.dry_run:
        logger.info("DONE: Dry-run; no backup executed. MQTT=%s Email=%s log=%s", mqtt_result, email_result, logfile)
        return rc or (3 if "failed" in (mqtt_result, email_result) else 0)

    if rc == 0:
        logger.info("DONE: Backup succeeded. log=%s", logfile)
        return 0

    if nonempty_file(errfile):
        logger.error("DONE: Backup FAILED (rc=%d). log=%s err=%s", rc, logfile, errfile)
    else:
        logger.error("DONE: Backup FAILED (rc=%d). log=%s", rc, logfile)
    return rc
