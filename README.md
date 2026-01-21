# Proxmox → PBS Backup with MQTT Status

## ⚠️ Disclaimer / Liability

**Use this script at your own risk.**

The author takes **no responsibility or liability** for any data loss, service disruption, misconfiguration, or other damage that may occur from using this script.

Before running it in production, you **must**:

- Read the entire source code
- Understand exactly what it does
- Review and adapt it to your own environment
- Test it carefully in a non‑production setup

By using this script, **you accept full responsibility** for its effects.

---

## Overview

This script performs a **full Proxmox VE backup** (VMs and containers) to a **Proxmox Backup Server (PBS)** datastore using `vzdump`, and then **publishes the backup result to MQTT**.

It is designed for automation and monitoring (for example via Home Assistant, Node‑RED, or other MQTT consumers).

### Key features

- Runs `vzdump` on a Proxmox VE node  
- Supports backing up **all VMs/CTs** or selected VMIDs  
- Streams backup output live to the terminal  
- Writes detailed logs to `.log` and `.err` files  
- Publishes an MQTT JSON message on **both success and failure**  
- Optional TLS, authentication, QoS, and retained MQTT messages  
- Dry‑run mode for safe testing  

---

## Requirements

### System

- Proxmox VE node (must be run **on the Proxmox host**, not on PBS)
- Root privileges (`sudo` or root shell)
- `vzdump` available in `$PATH`

### Python

- Python 3.9+
- Required module:

```bash
pip install paho-mqtt
```

---

## What the Script Does (High‑Level Flow)

1. Validates environment (root, `vzdump`, MQTT library)
2. Builds a `vzdump` command based on CLI arguments
3. Executes the backup while streaming output live
4. Writes logs to:
   - `*.log` (full output)
   - `*.err` (only attached to MQTT if non‑empty)
5. Publishes a final MQTT message containing:
   - success / error state
   - return code
   - runtime duration
   - node name
   - storage target
   - log file paths

MQTT is published **regardless of success or failure**.

---

## MQTT Payload Format

Example payload:

```json
{
  "status": "success",
  "rc": 0,
  "node": "pve-node1",
  "storage": "PBS-Backup:Datastore1",
  "duration_s": 842,
  "ts": "2026-01-21T04:58:12",
  "log_file": "/var/log/pbs-backup/pbs-backup-2026-01-21_04-44-10.log",
  "err_file": null
}
```

---

## Usage Examples

### Backup everything to PBS and publish MQTT

```bash
sudo ./pbs_backup.py   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

### Backup selected VMIDs only

```bash
sudo ./pbs_backup.py   --no-all   --vmid 100 101 102   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

### Dry‑run (no backup executed)

```bash
--dry-run
```

---

## Logging

Default log directory:

```
/var/log/pbs-backup/
```

---

## Security Considerations

- MQTT credentials are passed via CLI → visible in process list
- Use TLS and restricted users on your broker
- Restrict script execution permissions
- Always review the code before upgrades

---

## License

No warranty is provided.

You may use and modify this script freely, but **you are solely responsible** for its behavior and consequences.
