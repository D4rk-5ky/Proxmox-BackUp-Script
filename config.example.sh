#!/usr/bin/env bash
# Source from Bash after reviewing/editing values; this file executes no backup.
# Normal runs use config.toml automatically; this optional array shows CLI overrides.
# --config /path/to/settings.toml selects an alternative file. See README.md for precedence.
# Usage: source ./config.example.sh
#        sudo ./pbs-backup "${PBS_BACKUP_ARGS[@]}"
# Standalone inspection commands (no required flags):
#   ./pbs-backup -h           # Same as --help: explain every flag, then exit.
#   ./pbs-backup --version   # Show installed application version, then exit.

PBS_BACKUP_ARGS=(
  --all                                # Default: all guests on this node.
  # --no-all                           # Replace --all; requires --vmid below.
  # --vmid 100 101                     # Only with --no-all; positive guest IDs.
  # --exclude 105 106                  # Exclude these IDs; no empty list.
  --storage pbs-storage                # REQUIRED: configured PVE storage ID.
  --mode snapshot                      # Default; alternatives: suspend or stop.
  --compress zstd                      # Default; passed through to vzdump.
  --bwlimit 0                          # Default: unlimited; KiB/s when positive.
  # --only-running                     # Default off; read-only pvesh query, fail if none match.
  # --quiet                            # Default off; reduce vzdump output only.
  # --timeout 14400                    # Positive seconds; default has no deadline.
  # --notes-template '{{guestname}} on {{node}}'  # Optional; literal Proxmox template.
  --dry-run                            # No backup; notifications off unless enabled below.
  # --dry-run-mqtt                     # Optional labelled preview at <topic>/dry-run, not retained.
  # --dry-run-email                    # Optional labelled sendmail test; requires --mailto.
  # --mailto admin@example.com         # Optional PVE email recipient(s).
  # --mailnotification failure         # Optional; e.g. always/failure, PVE-dependent.
  --log-dir logs                       # Default: logs/ beside the real script.
  --log-prefix pbs-backup               # Default filename prefix, no directories.
  --mqtt-host mqtt.example.lan          # REQUIRED: broker host/IP.
  --mqtt-port 1883                      # Default; set e.g. 8883 if enabling TLS.
  --mqtt-topic proxmox/backup/pve1       # REQUIRED: topic, no + or # wildcards.
  # --mqtt-user backupbot              # Optional broker username.
  # --mqtt-pass CHANGE_ME              # Requires user; exposed in process arguments.
  --mqtt-qos 1                         # Default; alternatives 0 (local send), 2.
  # --mqtt-retain                      # Default off; store final status on broker.
  --mqtt-timeout 15                    # Default publish wait seconds, not connection deadline.
  # --mqtt-client-id pve1-nightly       # Default: proxmox-backup-<node>.
  # --mqtt-tls                         # Default off; verified TLS, set correct port.
  # --mqtt-cafile /etc/ssl/certs/backup-ca.pem  # TLS only; default system trust.
  # --mqtt-insecure                    # Default off; TLS only, unsafe hostname bypass.
)
