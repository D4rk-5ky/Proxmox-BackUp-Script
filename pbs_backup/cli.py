"""TOML loading, optional CLI overrides and shared input validation."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Dict

from . import __version__
from .notifications import dry_run_recipients

# The launcher and user config live above this package, not inside it.
SCRIPT_DIR = Path(__file__).resolve().parent.parent

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

# TOML keys use the existing argparse destinations; MQTT drops its repeated prefix.
CONFIG_SECTIONS = {
    "selection": ("all", "vmid", "exclude"),
    "backup": ("storage", "mode", "compress", "bwlimit", "only_running", "quiet",
               "timeout", "notes_template", "dry_run", "dry_run_mqtt", "dry_run_email"),
    "mail": ("mailto", "mailnotification"),
    "logging": ("log_dir", "log_prefix"),
    "mqtt": ("mqtt_host", "mqtt_port", "mqtt_topic", "mqtt_user", "mqtt_pass",
             "mqtt_qos", "mqtt_retain", "mqtt_timeout", "mqtt_client_id",
             "mqtt_tls", "mqtt_cafile", "mqtt_insecure"),
}


def load_config(path: Path, parser: argparse.ArgumentParser) -> Dict[str, Any]:
    """Read strict TOML defaults using existing CLI types, choices, and destinations."""
    if tomllib is None:
        parser.error("TOML requires Python 3.11+ or 'tomli' on Python 3.9/3.10 (pip install tomli).")
    try:
        with path.open("rb") as source:
            data = tomllib.load(source)
    except OSError:
        parser.error(f"Cannot read TOML config: {path}. Copy config.example.toml to config.toml, edit it, or use --config PATH.")
    except ValueError:
        # Do not echo parser excerpts that could contain a password.
        parser.error(f"Invalid TOML syntax in {path}; check quoting, tables, and duplicate keys.")
    actions = {action.dest: action for action in parser._actions}
    defaults: Dict[str, Any] = {}
    seen_sections = set()
    for raw_section, values in data.items():
        # Category spelling is flexible; keys remain strict to catch setting typos.
        section = raw_section.lower()
        if section in seen_sections:
            parser.error(f"Duplicate TOML category (case-insensitive): {raw_section}.")
        seen_sections.add(section)
        if section not in CONFIG_SECTIONS or not isinstance(values, dict):
            parser.error(f"Unknown or invalid TOML section: {section}.")
        keys = {dest.removeprefix("mqtt_") if section == "mqtt" else dest: dest
                for dest in CONFIG_SECTIONS[section]}
        for key, value in values.items():
            label = f"{section}.{key}"
            if key not in keys:
                parser.error(f"Unknown TOML option: {label}.")
            dest = keys[key]
            action = actions[dest]
            if dest in ("vmid", "exclude"):
                if not isinstance(value, list) or any(type(item) not in (str, int) for item in value):
                    parser.error(f"{label} must be an array of guest IDs (strings or integers).")
                value = [str(item) for item in value]
            elif isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
                if type(value) is not bool:
                    parser.error(f"{label} must be true or false (without quotes).")
            elif action.type is int:
                if type(value) is not int:
                    parser.error(f"{label} must be an integer.")
                if dest == "timeout" and value == 0:
                    value = None  # TOML has no null; zero means disabled in the config only.
            else:
                if not isinstance(value, str):
                    parser.error(f"{label} must be a quoted string.")
                if action.default is None and value == "":
                    value = None
            if action.choices is not None and value not in action.choices:
                parser.error(f"{label} must be one of: {', '.join(map(str, action.choices))}.")
            defaults[dest] = value
    if defaults.get("mqtt_cafile"):
        ca = Path(defaults["mqtt_cafile"]).expanduser()
        defaults["mqtt_cafile"] = str(ca if ca.is_absolute() else path.parent / ca)
    return defaults


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Load settings from config.toml beside this script. Optional flags override TOML. Dry-run notifications require explicit opt-in.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--config", default=str(SCRIPT_DIR / "config.toml"), help="TOML settings file; relative paths use the working directory.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sel = p.add_argument_group("Selection")
    selection = sel.add_mutually_exclusive_group()
    selection.add_argument("--all", action="store_true", default=True, help="Backup all VMs + CTs (default).")
    selection.add_argument("--no-all", dest="all", action="store_false", help="Select only --vmid guests (all-guests default: %(default)s); requires --vmid.")
    sel.add_argument("--vmid", nargs="+", default=[], help="VMID(s) when --no-all is used. Example: --vmid 100 101")
    sel.add_argument("--exclude", nargs="+", default=[], help="Exclude VMID(s) from all or selected guests. Example: --exclude 101 102")

    vzd = p.add_argument_group("Backup options")
    vzd.add_argument("--storage", default=None, help='Configured Proxmox VE storage ID, e.g. "pbs-storage" (PBS datastore is configured in PVE).')
    vzd.add_argument("--mode", choices=["snapshot", "suspend", "stop"], default="snapshot", help="vzdump backup mode; suspend/stop can interrupt guests.")
    vzd.add_argument("--compress", default="zstd", help="Compression value passed to installed vzdump; support depends on PVE/backend.")
    vzd.add_argument("--bwlimit", type=int, default=0, help="I/O bandwidth limit in KiB/s (0=unlimited).")
    vzd.add_argument("--only-running", action="store_true", help="Use pvesh to select guests running on this node at query time; fail if none match.")
    vzd.add_argument("--quiet", action="store_true", help="Reduce vzdump output; wrapper and MQTT logs remain visible.")
    vzd.add_argument("--timeout", type=int, default=None, help="Positive seconds before killing the direct vzdump process; otherwise use TOML timeout (0 disables it).")
    vzd.add_argument("--notes-template", default=None, help="vzdump template, e.g. '{{guestname}} on {{node}}'; passed literally.")
    vzd.add_argument("--dry-run", action="store_true", help="Preview without backup; notifications are off unless dry-run-mqtt/email is enabled; preflight checks remain.")

    vzd.add_argument("--dry-run-mqtt", action="store_true", help="During dry-run only, publish a labelled non-retained preview to <mqtt-topic>/dry-run.")
    vzd.add_argument("--dry-run-email", action="store_true", help="During dry-run only, submit a labelled preview email via local sendmail to --mailto (30-second submission timeout).")

    mail = p.add_argument_group("vzdump email options (optional)")
    mail.add_argument("--mailto", default=None, help="vzdump email recipients; depends on PVE notification configuration, independent of MQTT.")
    mail.add_argument("--mailnotification", default=None, help='vzdump email policy, e.g. always or failure; passed through to installed PVE.')

    log = p.add_argument_group("Logging")
    log.add_argument("--log-dir", default="logs", help="Log directory; relative paths are anchored beside the script; created automatically.")
    log.add_argument("--log-prefix", default="pbs-backup", help="Log filename prefix, without directory components.")

    mqttg = p.add_argument_group("MQTT")
    mqttg.add_argument("--mqtt-host", default=None, help="MQTT broker host/IP")
    mqttg.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port (1..65535); TLS does not change the port automatically.")
    mqttg.add_argument("--mqtt-topic", default=None, help="MQTT topic (e.g. proxmox/backup/pbs)")
    mqttg.add_argument("--mqtt-user", default=None, help="MQTT username (optional)")
    mqttg.add_argument("--mqtt-pass", default=None, help="MQTT password; requires --mqtt-user; visible in process arguments.")
    mqttg.add_argument("--mqtt-qos", type=int, default=1, choices=[0, 1, 2], help="QoS: 0 local send, 1 at least once, 2 exactly once at protocol level.")
    mqttg.add_argument("--mqtt-retain", action="store_true", help="Broker retains final status for later subscribers; omission does not clear old retained status.")
    mqttg.add_argument("--mqtt-timeout", type=int, default=15, help="Positive seconds to wait for publish completion; not a total connection timeout.")
    mqttg.add_argument("--mqtt-client-id", default=None, help="MQTT client ID; auto is proxmox-backup-<node>; use unique IDs for concurrent clients.")

    tls = p.add_argument_group("MQTT TLS")
    tls.add_argument("--mqtt-tls", action="store_true", help="Enable verified TLS; choose the broker TLS port explicitly (often 8883).")
    tls.add_argument("--mqtt-cafile", default=None, help="Custom trusted CA file; requires --mqtt-tls; omitted uses system trust.")
    tls.add_argument("--mqtt-insecure", action="store_true", help="Disable TLS hostname verification; requires --mqtt-tls; unsafe for production.")

    initial = p.parse_args()  # Help/version exit here without reading config or secrets.
    config_path = Path(initial.config).expanduser().resolve()
    p.set_defaults(**load_config(config_path, p))
    args = p.parse_args()
    args.config = str(config_path)
    if args.all and args.vmid:
        p.error("--vmid requires --no-all; refusing to select all guests.")
    if not args.all and not args.vmid:
        p.error("--no-all requires --vmid.")
    for option in ("vmid", "exclude"):
        values = getattr(args, option)
        if any(not value.isascii() or not value.isdecimal() or int(value) <= 0 for value in values):
            p.error(f"--{option} requires positive numeric guest IDs.")
        setattr(args, option, [str(int(value)) for value in values])
    if args.bwlimit < 0:
        p.error("--bwlimit must be zero or positive.")
    if args.timeout is not None and args.timeout <= 0:
        p.error("--timeout must be positive; use BACKUP.timeout = 0 in TOML for no deadline.")
    if args.mqtt_timeout <= 0 or not 1 <= args.mqtt_port <= 65535:
        p.error("--mqtt-timeout must be positive and --mqtt-port must be 1..65535.")
    if any(not value or not value.strip() for value in (args.storage, args.mqtt_host, args.mqtt_topic)):
        p.error("Set BACKUP.storage, MQTT.host and MQTT.topic in TOML (or supply their CLI overrides).")
    if any(char in args.mqtt_topic for char in ("+", "#", "\x00")):
        p.error("--mqtt-topic must be a publish topic without wildcards or NUL.")
    if (args.mqtt_cafile or args.mqtt_insecure) and not args.mqtt_tls:
        p.error("--mqtt-cafile and --mqtt-insecure require --mqtt-tls.")
    if args.mqtt_pass is not None and not args.mqtt_user:
        p.error("--mqtt-pass requires --mqtt-user.")
    if not args.log_prefix or args.log_prefix in (".", "..") or os.path.basename(args.log_prefix) != args.log_prefix:
        p.error("--log-prefix must be a filename prefix, without directory components.")
    if args.dry_run and args.dry_run_email:
        try:
            dry_run_recipients(args.mailto)
        except ValueError as e:
            p.error(str(e))
    if not args.log_dir.strip():
        p.error("LOGGING.log_dir / --log-dir must not be empty.")
    directory = Path(args.log_dir).expanduser()
    args.log_dir = str(directory if directory.is_absolute() else SCRIPT_DIR / directory)
    return args
