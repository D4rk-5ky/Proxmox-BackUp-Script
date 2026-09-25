"""MQTT status publication and optional dry-run email through local sendmail."""
from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
from email.errors import HeaderParseError
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any, Dict, List, Optional

from .logging_utils import nonempty_file, now_iso

try:
    import paho.mqtt.client as mqtt  # type: ignore
except Exception:
    mqtt = None


def mqtt_publish(
    *,
    host: str,
    port: int,
    topic: str,
    payload: Dict[str, Any],
    username: Optional[str],
    password: Optional[str],
    tls: bool,
    cafile: Optional[str],
    insecure: bool,
    client_id: str,
    retain: bool,
    qos: int,
    logger: logging.Logger,
    timeout_sec: int = 15,
) -> None:
    if mqtt is None:
        raise RuntimeError("paho-mqtt not installed. Install with: pip install paho-mqtt")

    # Paho-mqtt 2.x supports callback_api_version; older versions don't.
    try:
        client = mqtt.Client(
            client_id=client_id,
            protocol=mqtt.MQTTv311,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
    except Exception:
        client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)

    if username:
        client.username_pw_set(username, password=password)

    if tls:
        client.tls_set(ca_certs=cafile if cafile else None)
        if insecure:
            client.tls_insecure_set(True)

    published = {"ok": False}

    def on_publish(_client, _userdata, mid, *args, **kwargs):
        published["ok"] = True
        logger.info("MQTT publish acknowledged (mid=%s)", mid)

    def on_disconnect(_client, _userdata, *args, **kwargs):
        # VERSION2 adds disconnect_flags before reason_code; VERSION1 starts at rc.
        reason = args[1] if len(args) >= 3 else args[0] if args else kwargs.get("reason_code", kwargs.get("rc"))
        logger.info("MQTT disconnected (reason=%s)", reason)

    try:
        client.on_publish = on_publish
        client.on_disconnect = on_disconnect
    except Exception:
        pass

    logger.info("Connecting MQTT %s:%d tls=%s ...", host, port, tls)
    client.connect(host, port, keepalive=30)

    client.loop_start()
    try:
        msg = json.dumps(payload, ensure_ascii=False)
        logger.info("Publishing MQTT topic=%s qos=%s retain=%s payload=%s", topic, qos, retain, msg)

        info = client.publish(topic, msg, qos=qos, retain=retain)

        info.wait_for_publish(timeout=timeout_sec)
        if not info.is_published() and not published["ok"]:
            raise TimeoutError(f"MQTT publish not acknowledged within {timeout_sec}s")
    finally:
        try:
            client.disconnect()
        finally:
            client.loop_stop()

    logger.info("MQTT published OK")


def publish_backup_status(
    *,
    rc: int,
    duration_s: int,
    node: str,
    storage: str,
    log_file: str,
    err_file: str,
    mqtt_host: str,
    mqtt_port: int,
    mqtt_topic: str,
    mqtt_user: Optional[str],
    mqtt_pass: Optional[str],
    mqtt_tls: bool,
    mqtt_cafile: Optional[str],
    mqtt_insecure: bool,
    mqtt_client_id: str,
    mqtt_retain: bool,
    mqtt_qos: int,
    mqtt_timeout: int,
    logger: logging.Logger,
    dry_run: bool = False,
) -> None:
    status = "dry-run" if dry_run else "success" if rc == 0 else "error"
    payload: Dict[str, Any] = {
        "status": status,
        "rc": None if dry_run else rc,
        "node": node,
        "storage": storage,
        "duration_s": duration_s,
        "ts": now_iso(),
        "log_file": log_file,
        "err_file": err_file if nonempty_file(err_file) else None,
    }

    if dry_run:
        payload.update(dry_run=True, backup_executed=False, preview_rc=rc)

    mqtt_publish(
        host=mqtt_host,
        port=mqtt_port,
        topic=mqtt_topic + "/dry-run" if dry_run else mqtt_topic,
        payload=payload,
        username=mqtt_user,
        password=mqtt_pass,
        tls=mqtt_tls,
        cafile=mqtt_cafile,
        insecure=mqtt_insecure,
        client_id=mqtt_client_id,
        retain=False if dry_run else mqtt_retain,
        qos=mqtt_qos,
        logger=logger,
        timeout_sec=mqtt_timeout,
    )


def dry_run_recipients(value: Optional[str]) -> List[str]:
    """Validate comma-separated bare addresses/local aliases without header injection."""
    if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Dry-run email requires MAIL.mailto with comma-separated addresses or local aliases.")
    recipients = [item.strip() for item in value.split(",")]
    for recipient in recipients:
        if not recipient or not recipient.isascii() or recipient.startswith("-"):
            raise ValueError("Dry-run email needs nonempty ASCII recipients, not command options.")
        if "@" not in recipient:
            if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*", recipient):
                raise ValueError("Dry-run email needs bare addresses or simple local aliases, separated by commas.")
        else:
            try:
                address = Address(addr_spec=recipient)
                if not address.username or not address.domain:
                    raise ValueError("incomplete address")
            except (ValueError, HeaderParseError, IndexError):
                # Older Python email parsers can raise IndexError for an empty domain.
                raise ValueError("Invalid dry-run email address; use bare addresses, not display names.") from None
    return recipients


def send_dry_run_email(
    *, mailto: str, node: str, storage: str, cmd: List[str],
    log_file: str, err_file: str, logger: logging.Logger,
) -> None:
    """Submit a labelled preview to the local mail service, never a backup command."""
    recipients = dry_run_recipients(mailto)
    sendmail = shutil.which("sendmail")
    if sendmail is None and os.access("/usr/sbin/sendmail", os.X_OK):
        sendmail = "/usr/sbin/sendmail"
    if sendmail is None:
        raise RuntimeError("sendmail not found; configure the host mail service for dry-run email.")
    message = EmailMessage()
    message["From"] = "PBS Backup <root>"
    message["To"] = ", ".join(recipients)
    message["Subject"] = f"[DRY-RUN] Proxmox backup preview on {node} - NO BACKUP EXECUTED"
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    message.set_content(
        "DRY-RUN ONLY: NO BACKUP EXECUTED. This is a notification test, not a backup result.\n\n"
        f"Node: {node}\nStorage: {storage}\nTime: {now_iso()}\n"
        f"Full log: {log_file}\nError log (if nonempty): {err_file}\n\n"
        f"Planned command (NOT executed):\n{shlex.join(cmd)}\n"
    )
    # -t reads only our validated To header; -i prevents dot-only body termination.
    # No recipient, config value, or planned backup command is executed by a shell.
    result = subprocess.run(
        [sendmail, "-i", "-t"], input=message.as_bytes(),
        capture_output=True, timeout=30, check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"sendmail failed (rc={result.returncode}): {detail}")
    logger.info("DRY-RUN email accepted by local mail service; inbox delivery is not confirmed.")
