# Proxmox → PBS backup with MQTT status

Copy **`config.example.toml`** to **`config.toml`**, edit your settings, then run **`sudo ./pbs-backup`**. Settings flags are not needed. The app backs up VMs and containers through `vzdump`, keeps full logs in a **`logs/` folder beside the script**, writes **only error messages to `.err`**, and attempts to publish the backup result to MQTT.

⚠️ AI-assisted / vibe-coded experimental software. Use at your own risk. Read the full disclaimer below before using this on real data.

## Installation and first run

Run on a **Proxmox VE host**, not on PBS. Requirements are Python 3.9+, root, `vzdump`, and `paho-mqtt`. Running-guest filtering additionally needs `pvesh`. Configure your PBS datastore as a storage target in PVE before using the app.

For the host's system Python:

```bash
sudo apt-get install python3-paho-mqtt
chmod +x pbs-backup
./pbs-backup --help
./pbs-backup --version
```

`apt-get install` installs the MQTT dependency. `chmod +x` makes the script directly executable. Help and version inspect the app without starting a backup, loading secrets, or requiring root.

Python 3.11+ includes the TOML reader. Python 3.9/3.10 also needs `tomli` (for example, install `python3-tomli` if available in your host's package repositories). The parser uses [Python's `tomllib` interface](https://docs.python.org/3/library/tomllib.html). If using a dedicated Python virtual environment, install dependencies there with `python -m pip install -r requirements.txt` and run that environment's interpreter explicitly, for example `sudo /path/to/venv/bin/python ./pbs-backup`.

Create your private settings file (the `-n` prevents overwriting existing settings):

```bash
cp -n config.example.toml config.toml
chmod 600 config.toml
```

Open `config.toml` in your editor. Fill these existing values; do not append duplicate tables or keys:

```toml
[BACKUP]
storage = "pbs-storage"
dry_run = true

[MQTT]
host = "mqtt.example.lan"
topic = "proxmox/backup/pve1"
```

The shipped file already includes all other settings and explanatory comments. Required destination values are deliberately blank until you configure them. `storage` is the **PVE storage ID** connected to PBS, not `storage:datastore`. The wrapper does not check that the selected backend is PBS.

Run a preview:

```bash
sudo ./pbs-backup
```

The shipped `dry_run = true` prints the resolved backup command and creates local logs. It never runs `vzdump`. MQTT and email are off by default; optional test notifications are described below and never report a successful backup. It still requires root, `vzdump`, and Paho; running-guest selection also performs a read-only inventory query. A preview does not test storage availability. Notification opt-ins can test MQTT publication or local email submission, subject to the delivery limits below.

After reviewing the preview, change **`dry_run = false`** in `[BACKUP]` and run the same command to perform the backup.

## Configuration rules and paths

- The default config is `config.toml` beside the **real script file**, even when invoked from another working directory or through a symbolic link.
- An alternative file is selected with `sudo ./pbs-backup --config /path/to/settings.toml`. A relative `--config` path starts at the shell's working directory.
- Relative `LOGGING.log_dir` values always start beside the script. Default `"logs"` creates that directory automatically. An absolute value explicitly selects another directory.
- A relative `MQTT.cafile` value in TOML starts beside the selected TOML file. A CLI `--mqtt-cafile` override uses the working directory. `~` is expanded for TOML CA paths, config paths, and log directory paths.
- Settings precedence is explicit CLI overrides, then TOML, then built-in defaults. Normal usage only needs TOML. Help displays built-in defaults, not your loaded file or password.
- Categories are `[SELECTION]`, `[BACKUP]`, `[MAIL]`, `[LOGGING]`, and `[MQTT]`. Category names are case-insensitive; keys stay lowercase. Repeating a category with different casing (such as `[MQTT]` and `[mqtt]`) is rejected, even with different keys.
- Unknown sections/keys, wrong types, invalid syntax/duplicate keys, and unreadable/missing config files stop the run. Syntax, key, type, and choice errors in the file are rejected even if a CLI override would replace that setting. Missing required destinations also stop the run.
- Strings need quotes; booleans are unquoted `true`/`false`; guest lists use arrays such as `[100, 101]`. Empty optional strings mean unset. TOML has no null: `BACKUP.timeout = 0` disables that deadline.
- TOML values are not shell commands, and environment variables such as `$PASSWORD` are not expanded. Passwords stored in TOML stay off the process command line, but the file is plaintext. Use `chmod 600 config.toml` to restrict access before saving secrets.

There is no automatically installed scheduler, config-writing command, restore operation, or log rotation. Preserve your configured TOML file when replacing the application during an update.

## Keeping settings out of Git

`.gitignore` excludes `config*.*` at any depth (including case variants, JSON, YAML, shell files and backup copies), plus all TOML files. The root `config.example.toml` is the **only config exception**. Keep its placeholder values free of credentials. Runtime logs, bytecode, build caches and temporary files are also ignored.

Git ignore rules apply to untracked files; they do not remove files already committed, prevent forced additions, or erase repository history. To stop tracking an already tracked `config.toml` while keeping it on disk, run `git rm --cached -- config.toml`, then commit that change. Use the actual path for another tracked private config. `git check-ignore -v --no-index config.toml` shows the applicable ignore rule; `git status --short --untracked-files=all` shows what Git would report as changed or untracked.

The ZIP retains `config.example.sh` and `pbs-backup.toml` to preserve existing project files. Both contain placeholders and are ignored by Git. The Bash file remains an optional override example; the retained TOML may be explicitly selected with `--config pbs-backup.toml`, but neither is automatically loaded. Normal setup uses `config.example.toml` and your private `config.toml`. The ZIP contains no private `config.toml`.

## Every configuration option

All 30 settings are present and commented in `config.example.toml`, ready to copy into `config.toml`. The tables show their meanings and optional CLI equivalents. Boolean CLI switches enable their setting; to disable a TOML-enabled boolean, edit TOML. `--no-all` is the explicit selection exception.

### `[SELECTION]`

| Key / optional flag | Default | Purpose and example |
| --- | --- | --- |
| `all` / `--all`, `--no-all` | `true` | Select all guests on this node. For a subset, set `all = false` and fill `vmid`. An all-guest request with nonempty `vmid` is rejected. |
| `vmid` / `--vmid ID ...` | `[]` | Explicit guest IDs, e.g. `[100, 101]` or `["100", "101"]`. Requires `all = false`; IDs must be positive numbers and are normalized. |
| `exclude` / `--exclude ID ...` | `[]` | Remove guests from all or explicit selection, e.g. `[105, 106]`. Removing every explicit guest stops the run. CLI form requires at least one ID. |

To back up guests 100 and 102, set:

```toml
[SELECTION]
all = false
vmid = [100, 101, 102]
exclude = [101]
```

To back up all except 105, use `all = true`, `vmid = []`, and `exclude = [105]`.

### `[BACKUP]`

| Key / optional flag | Default | Purpose and example |
| --- | --- | --- |
| `storage` / `--storage ID` | Required | PVE backup storage ID, e.g. `"pbs-storage"`. The shipped empty string prevents execution until configured. |
| `mode` / `--mode MODE` | `"snapshot"` | `"snapshot"`, `"suspend"`, or `"stop"`. Suspend/stop can interrupt guests; PVE governs backend-specific behavior. |
| `compress` / `--compress VALUE` | `"zstd"` | Compression passed through to installed `vzdump`; support/effect depends on PVE and backend. |
| `bwlimit` / `--bwlimit N` | `0` | Nonnegative I/O limit in KiB/s. `0` means unlimited; example `250000`. |
| `only_running` / `--only-running` | `false` | Query `pvesh` for local running QEMU/LXC guests and apply selection/exclusions. Query deadline is 30 seconds; failure or no matches stops execution. |
| `quiet` / `--quiet` | `false` | Reduce `vzdump` output, keeping script/MQTT logging enabled. |
| `timeout` / `--timeout N` | `0` in TOML | `0` means no backup deadline; positive seconds bound the direct subprocess, including silent output and exit waiting. Example `14400`. CLI form requires a positive integer. |
| `notes_template` / `--notes-template TEXT` | `""` | Optional literal PVE template, e.g. `"{{guestname}} on {{node}}"`; empty omits it. Other placeholders include `{{vmid}}` and `{{cluster}}`. |
| `dry_run` / `--dry-run` | Shipped `true` | Preview without executing a backup. Set `false` to execute. If omitted, the built-in default is `false`. Notifications require the independent opt-ins below. |
| `dry_run_mqtt` / `--dry-run-mqtt` | `false` | During dry-run only, send a labelled MQTT preview to `<MQTT.topic>/dry-run`, always non-retained. Uses existing broker/auth/TLS/QoS/timeout. Does not enable dry-run itself. |
| `dry_run_email` / `--dry-run-email` | `false` | During dry-run only, submit a labelled test email via local `sendmail` to `MAIL.mailto`. Submission timeout: 30 seconds. Does not enable dry-run itself. |

Running status is a snapshot: guests can stop or migrate after selection. A backup timeout kills/reaps **only the directly launched subprocess**, so Proxmox task workers may continue. Inspect the PVE task before retrying an interrupted run. This app does not unlock guests, terminate other jobs, override retention policies, or verify restores. PVE/storage settings still govern unexposed options.

### `[MAIL]`

| Key / optional flag | Default | Purpose and example |
| --- | --- | --- |
| `mailto` / `--mailto RECIPIENTS` | `""` | Optional PVE email recipient(s), e.g. `"admin@example.com"`; independent of MQTT. |
| `mailnotification` / `--mailnotification VALUE` | `""` | Optional policy passed through to installed PVE, commonly `"always"` or `"failure"`; empty uses host behavior. |

Real-backup email requires working PVE notification delivery. PVE's notification-system mode can ignore these legacy mail arguments. Dry-run email instead uses the local mail service directly, with the same `mailto` setting; it is independent of `mailnotification`.

### `[LOGGING]`

| Key / optional flag | Default | Purpose and example |
| --- | --- | --- |
| `log_dir` / `--log-dir PATH` | `"logs"` | Create/use `logs/` beside the real script. Other relative paths remain script-relative; absolute paths explicitly override the location. |
| `log_prefix` / `--log-prefix TEXT` | `"pbs-backup"` | Filename prefix without directory components, e.g. `"pve1-nightly"`. |

Files use `<prefix>-YYYY-MM-DD_HH-MM-SS_microseconds-PID.log` and `.err`. Microseconds and process ID distinguish simultaneous runs. Timestamps use local time.

- **`.log`** contains all captured child stdout/stderr and script/MQTT messages, including progress, warnings, and errors.
- **`.err`** contains child lines explicitly prefixed `ERROR:`, `TASK ERROR:`, `FATAL:`, or `CRITICAL:` (case-insensitive; optional guest-ID/timestamp prefixes are supported), plus script records at ERROR severity or higher. These include runtime preflight, command-launch, timeout, nonzero-exit summaries, and MQTT failures.
- Ordinary stderr is **not automatically an error**: PVE also writes progress there. INFO/WARN messages and successful completion messages do not enter `.err`. See the [Proxmox logging implementation](https://raw.githubusercontent.com/proxmox/pve-guest-common/master/src/PVE/VZDump/Plugin.pm).
- A successful run with no recognized errors has an empty `.err`; a clean dry-run may have no `.err` at all. An explicit error line can still be captured even if the child exits 0. The exit code remains the source of backup status.
- Unlabelled diagnostics and continuation lines remain in the full `.log`. If a command fails without an explicit error line, `.err` still receives its failure summary and points to the full log. This filter does not attempt to infer arbitrary text semantics.

Logs are initialized after config validation and before runtime preflight, so root/tool/selection errors can be recorded. Config/CLI parse errors go to terminal stderr before a log path is trusted. If the log destination is unwritable, the app stops before backing up and reports the logging failure to terminal stderr. Logs are not automatically rotated or deleted.

### `[MQTT]`

| Key / optional flag | Default | Purpose and example |
| --- | --- | --- |
| `host` / `--mqtt-host HOST` | Required | Broker hostname/IP, e.g. `"mqtt.example.lan"`. No URL scheme. |
| `port` / `--mqtt-port N` | `1883` | Integer 1–65535; TLS does not change it automatically. |
| `topic` / `--mqtt-topic TOPIC` | Required | Publish topic, e.g. `"proxmox/backup/pve1"`. Empty values, NUL, and `+`/`#` wildcards are rejected. |
| `user` / `--mqtt-user USER` | `""` | Optional username; empty selects anonymous connection. |
| `pass` / `--mqtt-pass PASSWORD` | `""` | Optional password, requiring a username when set. Prefer TOML so it does not appear in process arguments/history. |
| `qos` / `--mqtt-qos N` | `1` | `0`: local send; `1`: at least once; `2`: exactly once at MQTT protocol level. QoS 0 has no broker acknowledgement. |
| `retain` / `--mqtt-retain` | `false` | Retain the final message for future subscribers. Setting false does not erase an earlier retained message. |
| `timeout` / `--mqtt-timeout N` | `15` | Positive publish-completion wait in seconds. Does not bound DNS or connection establishment. |
| `client_id` / `--mqtt-client-id ID` | `""` | Empty generates `proxmox-backup-<node>`. Use unique IDs for concurrent clients. |
| `tls` / `--mqtt-tls` | `false` | Enable certificate/hostname-verified TLS. Set the broker TLS port explicitly, often 8883. |
| `cafile` / `--mqtt-cafile PATH` | `""` | Custom CA file; requires TLS. Empty uses system trust. Relative TOML paths are config-relative. |
| `insecure` / `--mqtt-insecure` | `false` | Explicitly disable TLS hostname verification; requires TLS. Unsafe for production. |

For TLS authentication, edit the existing MQTT section to set `tls = true`, `port = 8883` (or your broker's port), `user`, `pass`, and optionally `cafile = "certs/backup-ca.pem"`. Keep `insecure = false` for verified hostname checking.

## Optional MQTT and email during dry-run

Both options default to `false` and work independently. To test both, edit the existing sections in `config.toml`:

```toml
[BACKUP]
dry_run = true
dry_run_mqtt = true
dry_run_email = true

[MAIL]
mailto = "admin@example.com"
```

Keep your existing `BACKUP.storage` and `[MQTT]` settings configured. Run the same command, `sudo ./pbs-backup`. Set either notification option back to `false` to disable that channel. With `dry_run = false`, these two options are ignored: real backups retain their normal MQTT and `vzdump` email behavior, with no extra test email.

**MQTT preview:** the existing connection settings are reused, but the destination is the configured topic with `/dry-run` appended. For example, `proxmox/backup/pve1` becomes `proxmox/backup/pve1/dry-run`. Messages are never retained, even if `MQTT.retain = true`; the last real retained backup result is left intact. Broker permissions must allow that preview topic. Subscribe to the preview topic when testing.

The preview payload keeps node/storage/timing/log fields and adds these explicit markers:

```json
{
  "status": "dry-run",
  "rc": null,
  "dry_run": true,
  "backup_executed": false,
  "preview_rc": 0
}
```

`preview_rc` describes preview preparation, not a backup. Real-backup payload fields and their meanings are unchanged.

**Email preview:** the subject starts `[DRY-RUN]` and the subject/body state **NO BACKUP EXECUTED**. It includes node, storage, local log paths, and the planned command as text. No logs/config files or credentials are attached. `MAIL.mailto` must contain comma-separated bare ASCII email addresses (e.g. `"admin@example.com,ops@example.com"`) or simple local aliases such as `"root"`. Display-name forms and PVE user-to-email resolution are not supported for preview email; use actual email addresses rather than PVE user IDs.

The host needs a configured sendmail-compatible mail service, found in PATH or at `/usr/sbin/sendmail`. The script submits the message using `sendmail -i -t` with a fixed 30-second submission timeout. It does not invoke `vzdump` to generate mail or configure the relay. The invoking root user's envelope identity and local mail-service configuration control delivery; `mailnotification = "failure"` does not suppress an explicitly requested test message. Successful submission means the local service accepted it, not that the recipient's inbox received it. See the [Postfix sendmail interface](https://raw.githubusercontent.com/vdukhovni/postfix/master/postfix/man/man1/sendmail.1).

After config and runtime preflight succeed, every enabled notification channel is attempted once, independently. A send/submission failure is logged to `.err` and makes the dry-run exit **3**; the other enabled channel is still attempted. Missing/invalid recipients fail configuration validation with exit 2 before notifications. Preflight failures (including empty guest selection) still stop the run before any notification. No notification option bypasses root/tool/Paho checks or permits a dry-run backup.

## Commands

| Command | What it does |
| --- | --- |
| `sudo ./pbs-backup` | Load adjacent TOML, initialize logs, validate runtime prerequisites, then preview or execute according to `BACKUP.dry_run`. |
| `sudo ./pbs-backup --config /path/to/settings.toml` | Use a different TOML file; does not relocate the default logs folder. |
| `./pbs-backup -h` or `./pbs-backup --help` | Explain all optional CLI overrides and built-in defaults, then exit without reading TOML. |
| `./pbs-backup --version` | Print version and exit. |
| `sudo ./pbs-backup --dry-run` | Force preview mode for one invocation; TOML notification opt-ins still apply. |
| `sudo ./pbs-backup --dry-run --dry-run-mqtt` | Force a preview and enable its MQTT test message. |
| `sudo ./pbs-backup --dry-run --dry-run-email --mailto admin@example.com` | Force a preview and enable its email test. |
| `python3 pbs-backup ...` | Use an explicitly chosen Python interpreter; real runs still need root. |
| `cp -n config.example.toml config.toml` | Create private settings without overwriting an existing file. |
| `chmod 600 config.toml` | Restrict read/write access to the file owner before storing credentials. |
| `python3 -B -m unittest discover -s tests -v` | Run the offline regression suite; `-B` suppresses bytecode caches. Requires TOML support, not root/PVE/MQTT. |
| `sha256sum -c RELEASE_MANIFEST.sha256` | On Linux, verify packaged file hashes from the extracted project directory. |

`config.example.sh` is an optional Bash array example for CLI overrides. To use it, edit its placeholders, run `source ./config.example.sh` in Bash, then `sudo ./pbs-backup "${PBS_BACKUP_ARGS[@]}"`. Sourcing only loads the array. A valid TOML file is still loaded; the array overrides its settings and includes dry-run. You can ignore this file when using TOML normally.

## MQTT status, exit codes, and troubleshooting

A real backup attempts one normal status publication. Opted-in dry-run publication uses the distinct preview topic and payload described above. Example after a clean success:

```json
{
  "status": "success",
  "rc": 0,
  "node": "pve1",
  "storage": "pbs-storage",
  "duration_s": 842,
  "ts": "2026-09-24T04:58:12",
  "log_file": "/opt/pbs-backup/logs/pbs-backup-2026-09-24_04-44-10_123456-4321.log",
  "err_file": null
}
```

`status` follows the backup return code (`0` = success, otherwise error). `duration_s` is whole seconds for execution, excluding guest selection and MQTT. `ts` is local publication time without a timezone offset. `node` is the uname nodename, and `storage` is the requested PVE ID. Log paths are host-local paths, not MQTT attachments. `err_file` is a path only when the error file is nonempty at payload creation; otherwise null. A later MQTT failure is logged locally and cannot revise a payload already created.

| Result | Meaning and action |
| --- | --- |
| Exit `0` | Backup succeeded, or preview and all requested notification operations completed. Email acceptance is not inbox delivery; this does not prove restore integrity. |
| Exit `2` | Config, CLI, logging initialization, runtime preflight, or selection failure; inspect terminal/logs. The backup child can also independently return 2. |
| Exit `3` during dry-run | At least one requested notification failed; inspect `.err` and broker/local mail-service settings. A real backup child may independently return 3. |
| Exit `255` | Caught command-launch/streaming error or timeout; inspect `.err`, full `.log`, and PVE task state. |
| Other child code | Passed through from `vzdump`. Negative signal return values are mapped by the OS when used as process exit status. |
| `MQTT publish failed` | Check broker/TLS/auth settings. The backup exit code is preserved; MQTT failure does not turn a successful backup into a failed backup. |
| No matching running guests | No backup or MQTT status is sent; check IDs, node name, inventory, and guest states. |
| Missing TOML reader | Use Python 3.11+ or install `tomli` into the interpreter running this script. |

Runtime interruption, disk failures, preflight errors, or an unavailable broker can prevent final MQTT delivery. Full Proxmox/PBS backup/restore and live MQTT/TLS behavior require testing on your own environment; see `VERIFICATION.md` for the checks performed with this release.

## ⚠️ Disclaimer / Liability

**Use this script at your own risk.**

The author takes **no responsibility or liability** for any data loss, service disruption, misconfiguration, service outage, missed backups, credential exposure, or other damage that may occur from using this script.

Before running it in production, you **must**:

- Read the entire source code
- Understand exactly what it does (and what it does *not* do)
- Review and adapt it to your own environment
- Test it carefully in a non‑production setup

By using this script, **you accept full responsibility** for its effects.

⚠️ AI-assisted / vibe-coded experimental software. Use at your own risk.

## Disclaimer

This project is AI-assisted / vibe-coded software created as a hobby project. It has not been professionally audited and may contain bugs, unsafe behavior, data-loss issues, security problems, or incorrect assumptions.

You are responsible for reviewing the code, testing it in a safe environment, making backups, and understanding what it does before using it on real data. The author is not responsible for damage, data loss, broken systems, security issues, or other problems caused by using this software.


## License

No warranty is provided.

You may use and modify this script freely, but **you are solely responsible** for its behavior and consequences.
