# Proxmox → PBS Backup with MQTT Status

## ⚠️ Disclaimer / Liability

**Use this script at your own risk.**

The author takes **no responsibility or liability** for any data loss, service disruption, misconfiguration, service outage, missed backups, credential exposure, or other damage that may occur from using this script.

Before running it in production, you **must**:

- Read the entire source code
- Understand exactly what it does (and what it does *not* do)
- Review and adapt it to your own environment
- Test it carefully in a non‑production setup

By using this script, **you accept full responsibility** for its effects.

---

## Overview

This script performs a **Proxmox VE backup** (VMs and containers) to a **Proxmox Backup Server (PBS)** datastore using `vzdump`, and then **publishes the backup result to MQTT**.

It is designed for automation and monitoring (for example via Home Assistant, Node‑RED, or other MQTT consumers).

### Key features

- Runs `vzdump` on a Proxmox VE node
- Supports backing up **all VMs/CTs** or **selected VMIDs**
- Streams backup output live to the terminal
- Writes logs to `.log` and `.err` files
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
   - `*.err` (combined stream; referenced in MQTT only if non‑empty)
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

- `status`: `"success"` or `"error"`
- `rc`: return code from `vzdump` (0 = success)
- `err_file`: `null` when the `.err` file is empty or missing

---

## CLI Reference (Quick)

### Selection

- `--all` (default): backup all VMs + CTs
- `--no-all --vmid <id...>`: backup only specified VMIDs
- `--exclude <id...>`: exclude VMIDs (works with `--all` or `--no-all --vmid ...`)

### Backup options

- `--storage "PBS-Backup:Datastore1"` (**required**)
- `--mode snapshot|suspend|stop` (default: snapshot)
- `--compress <algo>` (default: zstd)
- `--bwlimit <KB/s>` (default: 0 = unlimited)
- `--only-running`
- `--quiet`
- `--timeout <seconds>`
- `--notes-template "<template>"`
- `--dry-run`

### vzdump email options (optional)

- `--mailto <email>`
- `--mailnotification <value>` (varies by Proxmox version; passed through)

### Logging

- `--log-dir <path>` (default: `/var/log/pbs-backup`)
- `--log-prefix <prefix>` (default: `pbs-backup`)

### MQTT

- `--mqtt-host <host>` (**required**)
- `--mqtt-port <port>` (default: 1883)
- `--mqtt-topic <topic>` (**required**)
- `--mqtt-user <user>` (optional)
- `--mqtt-pass <pass>` (optional)
- `--mqtt-qos 0|1|2` (default: 1)
- `--mqtt-retain`
- `--mqtt-timeout <sec>` (default: 15)
- `--mqtt-client-id <id>` (default: auto)

### MQTT TLS

- `--mqtt-tls`
- `--mqtt-cafile <path>` (optional)
- `--mqtt-insecure` (skip hostname verification)

---

## Usage Examples (covers every flag / combination category)

> Note: “all combinations” in practice would be an enormous number of permutations.
> The examples below are written to **cover every flag at least once**, plus the most
> common real‑world combinations.

### 0) Minimal required flags (defaults: `--all`, `--mode snapshot`, `--compress zstd`)

```bash
sudo ./pbs_backup.py   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

---

### 1) Selection combinations

#### 1A) Default: backup all (explicit `--all`)

```bash
sudo ./pbs_backup.py   --all   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

#### 1B) Backup all but exclude some VMIDs (`--exclude` with `--all`)

```bash
sudo ./pbs_backup.py   --all   --exclude 101 105   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

#### 1C) Backup specific VMIDs (`--no-all` + `--vmid`)

```bash
sudo ./pbs_backup.py   --no-all   --vmid 100 101 102   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

#### 1D) Backup specific VMIDs but exclude some (`--no-all --vmid ... --exclude ...`)

```bash
sudo ./pbs_backup.py   --no-all   --vmid 100 101 102 105   --exclude 101   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

---

### 2) Backup option combinations

#### 2A) Choose mode: snapshot / suspend / stop

```bash
# snapshot (default)
sudo ./pbs_backup.py --storage "PBS-Backup:Datastore1" --mqtt-host 10.0.0.10 --mqtt-topic proxmox/backup/pbs --mode snapshot
# suspend
sudo ./pbs_backup.py --storage "PBS-Backup:Datastore1" --mqtt-host 10.0.0.10 --mqtt-topic proxmox/backup/pbs --mode suspend
# stop
sudo ./pbs_backup.py --storage "PBS-Backup:Datastore1" --mqtt-host 10.0.0.10 --mqtt-topic proxmox/backup/pbs --mode stop
```

#### 2B) Compression and bandwidth limit

```bash
sudo ./pbs_backup.py   --storage "PBS-Backup:Datastore1"   --compress zstd   --bwlimit 250000   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

#### 2C) Only running guests + quieter output

```bash
sudo ./pbs_backup.py   --only-running   --quiet   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

#### 2D) Timeout the vzdump run

```bash
sudo ./pbs_backup.py   --timeout 14400   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

#### 2E) Notes template (passed to `vzdump`)

```bash
sudo ./pbs_backup.py   --notes-template "Backup on {node} at {date}"   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

#### 2F) Dry-run (build + print actions, do not execute)

```bash
sudo ./pbs_backup.py   --dry-run   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

---

### 3) vzdump email options (optional)

> These options are passed straight to `vzdump`. They are **independent** of MQTT.

```bash
sudo ./pbs_backup.py   --mailto you@example.com   --mailnotification always   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

---

### 4) Logging combinations

#### 4A) Custom log directory

```bash
sudo ./pbs_backup.py   --log-dir "/root/logs/pbs-backup"   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

#### 4B) Custom log prefix

```bash
sudo ./pbs_backup.py   --log-prefix "pve1-nightly"   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

#### 4C) Custom log dir + prefix together

```bash
sudo ./pbs_backup.py   --log-dir "/root/logs/pbs-backup"   --log-prefix "pve1-nightly"   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

---

### 5) MQTT combinations (auth, QoS, retain, port, client-id, timeout)

#### 5A) Non-default port

```bash
sudo ./pbs_backup.py   --mqtt-port 1884   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

#### 5B) Username/password authentication

```bash
sudo ./pbs_backup.py   --mqtt-user "backupbot"   --mqtt-pass "CHANGE_ME"   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

#### 5C) QoS level

```bash
# qos 0
sudo ./pbs_backup.py --mqtt-qos 0 --storage "PBS-Backup:Datastore1" --mqtt-host 10.0.0.10 --mqtt-topic proxmox/backup/pbs
# qos 1 (default)
sudo ./pbs_backup.py --mqtt-qos 1 --storage "PBS-Backup:Datastore1" --mqtt-host 10.0.0.10 --mqtt-topic proxmox/backup/pbs
# qos 2
sudo ./pbs_backup.py --mqtt-qos 2 --storage "PBS-Backup:Datastore1" --mqtt-host 10.0.0.10 --mqtt-topic proxmox/backup/pbs
```

#### 5D) Retained message + custom client-id + custom timeout

```bash
sudo ./pbs_backup.py   --mqtt-retain   --mqtt-client-id "pve1-backup-job"   --mqtt-timeout 30   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

---

### 6) MQTT TLS combinations

#### 6A) TLS enabled (broker must support TLS)

```bash
sudo ./pbs_backup.py   --mqtt-tls   --mqtt-port 8883   --storage "PBS-Backup:Datastore1"   --mqtt-host mqtt.example.lan   --mqtt-topic proxmox/backup/pbs
```

#### 6B) TLS with custom CA file

```bash
sudo ./pbs_backup.py   --mqtt-tls   --mqtt-cafile "/etc/ssl/certs/your-ca.pem"   --mqtt-port 8883   --storage "PBS-Backup:Datastore1"   --mqtt-host mqtt.example.lan   --mqtt-topic proxmox/backup/pbs
```

#### 6C) TLS insecure (skip hostname verification; not recommended)

```bash
sudo ./pbs_backup.py   --mqtt-tls   --mqtt-insecure   --mqtt-port 8883   --storage "PBS-Backup:Datastore1"   --mqtt-host 10.0.0.10   --mqtt-topic proxmox/backup/pbs
```

---

### 7) “Everything together” (full combination example)

This example uses **most flags at once** to show a realistic “kitchen sink” configuration:

```bash
sudo ./pbs_backup.py   --no-all   --vmid 100 101 102 105   --exclude 101   --mode snapshot   --compress zstd   --bwlimit 250000   --only-running   --timeout 14400   --notes-template "PVE backup {node} {date}"   --mailto you@example.com   --mailnotification always   --log-dir "/root/logs/pbs-backup"   --log-prefix "pve1-nightly"   --mqtt-host mqtt.example.lan   --mqtt-port 8883   --mqtt-topic proxmox/backup/pbs   --mqtt-user "backupbot"   --mqtt-pass "CHANGE_ME"   --mqtt-qos 1   --mqtt-retain   --mqtt-timeout 30   --mqtt-client-id "pve1-backup-job"   --mqtt-tls   --mqtt-cafile "/etc/ssl/certs/your-ca.pem"
```

---

## Logging

Default log directory:

```
/var/log/pbs-backup/
```

Each run creates:

- `<prefix>-YYYY-MM-DD_HH-MM-SS.log`
- `<prefix>-YYYY-MM-DD_HH-MM-SS.err`

The `.err` file path is included in MQTT only if the file is non‑empty.

---

## Security Considerations

- MQTT credentials passed via CLI can be visible in:
  - `ps aux`
  - shell history
- Prefer:
  - Restricted broker users
  - TLS (`--mqtt-tls`)
  - Secrets handling via wrapper scripts or environment-secured execution
- Restrict script file permissions and who can run it
- Logs may contain sensitive information (paths, node names, guest IDs)

---

## License

No warranty is provided.

You may use and modify this script freely, but **you are solely responsible** for its behavior and consequences.
