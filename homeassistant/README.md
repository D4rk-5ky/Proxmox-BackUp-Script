# Home Assistant automation for pbs-backup 0.0.6

Use `pbs-backup.yaml` to replace the supplied automation in Home Assistant's **Edit in YAML** editor. It is a complete single-automation mapping. If maintaining `automations.yaml` manually, it must instead be one list item with the appropriate indentation; do not paste this mapping directly over that whole file. Replace the existing automation rather than leaving two copies enabled.

The full project includes this automation. Its notification-format and per-outcome switches are configured in YAML; application delivery settings are configured in TOML.

## Generic names and MQTT topics

The YAML has no hard-coded machine name. Replace the generic status topic `proxmox/backup/status` and command topic `proxmox/pbs/commands` with your chosen topics. The single status trigger receives dry-run and real results on exactly `MQTT.topic`. No preview suffix is used.

This anonymizes the reusable YAML, not the live data. Received MQTT JSON and notifications still contain the node, storage and log paths sent by the script, as requested by the JSON notification options. No runtime payload redaction is performed.

## Active script configuration

Edit the existing categories in **config.toml** beside `pbs-backup`. Do not append duplicate categories, and keep your current storage, broker, authentication and TLS settings.

```toml
[BACKUP]
dry_run = true
dry_run_mqtt = true

[MQTT]
enabled = true
on_success = true
topic = "proxmox/backup/status"
retain = false
```

These are selected settings illustrating the generic topic names, not a replacement for the complete config. If your existing config already uses another topic, keep it and set the YAML triggers to match it. All outcomes use the same topic. `on_success = true` is required for real-success notifications and the success-only maintenance request; the application default false suppresses those events. Failures remain published when MQTT is enabled, regardless of on_success. Setting `retain = false` prevents new normal results from being retained; dry-run MQTT is always non-retained regardless of this setting.

Run `sudo ./pbs-backup` on the Proxmox host. Dry-run still requires root, vzdump and Paho, along with configured required destinations. `dry_run_mqtt = true` opts into sending a real MQTT preview, but never starts a backup. Set `dry_run = false` to return to real backups. Set `dry_run_mqtt = false` if previews should stop notifying Home Assistant.

`BACKUP.dry_run_email` is a separate optional local-sendmail test. Home Assistant's Pushover preview notification works independently and does not require enabling script email. A preview's `preview_rc` describes preview command preparation, not final email delivery or the overall notification outcome; MQTT does not contain the final script exit code or an email-result field. Inspect the script exit status and .err for those results.

## YAML-only notification switches

Edit the `variables` block near the top of the YAML. Every switch below is enabled by default; use unquoted `true`/`false`.

```yaml
variables:
  notification_settings:
    dry_run:
      pushover: true
      persistent: true
    success:
      pushover: true
      persistent: true
    failure:
      pushover: true
      persistent: true
  pushover_include_mqtt_json: true
  persistent_include_mqtt_json: true
```

Each outcome has independent delivery switches. For example, `failure.pushover: false` suppresses failed-backup push notifications while leaving its persistent notifications available. The two JSON-format switches apply to all three outcomes independently for each channel. Turning JSON off still sends readable status, host/storage, timings, return code and log/error paths. Turning a channel off sends no notification through that channel for the selected outcome.

These notification preferences require **only YAML edits**. Existing script-side `dry_run_mqtt` must already be enabled for Home Assistant to receive a preview at all; the YAML cannot receive an MQTT message the script never sends. No Python editing is needed; use these files with the bundled application.

## Notification contents and JSON size

Persistent notifications include a readable summary and, when enabled, the complete MQTT payload as formatted JSON in a code block. Pushover includes a clear outcome label and compact JSON when enabled. All received JSON fields are included, including additional fields; JSON numbers, null and booleans are preserved. This is the received MQTT JSON displayed as notification text, not a new MQTT status publication.

Normal payloads fit in one push. [Pushover limits messages to 1,024 characters](https://pushover.net/api#limits). When a complete JSON payload plus the outcome label exceeds that limit, the YAML sends **multiple numbered push notifications**, each with a valid JSON envelope containing `part`, `parts` and `mqtt_json_fragment`. Concatenate the fragment strings in part order to recover the complete original JSON text. Every part retains its dry-run/success/failure label. Persistent notifications always keep the complete JSON together. If you prefer no multipart pushes, set `pushover_include_mqtt_json: false` and leave persistent JSON enabled.

With JSON disabled, an unusually long Pushover text summary is shortened with an explicit notice to fit the service limit. Normal short summaries remain complete. JSON itself is never silently cut off; delivery of every part still depends on the service.

## What each received result does

| Result | Home Assistant actions |
| --- | --- |
| Real `success` with integer `rc: 0`, on the base topic, without contradictory preview markers | Enabled persistent/Pushover notifications, then the existing verify/GC command. |
| Real `error` with nonzero integer rc, on the base topic, without contradictory preview markers | Enabled persistent/Pushover failure notifications; no maintenance command. Pushover failure notifications are now enabled by default. |
| Valid `dry-run` on the normal status topic, with `rc: null`, `dry_run: true`, `backup_executed: false` and integer `preview_rc` | Enabled persistent/Pushover notifications explicitly saying NO BACKUP EXECUTED; no maintenance command. |
| Malformed/non-object JSON, missing/invalid rc, unknown status, inconsistent markers, mismatched topic or manual Run actions without MQTT data | Persistent unknown-payload warning, independent of the three outcome switches. No maintenance command. |

Strict payload guards distinguish outcomes on the shared topic. A null rc is never converted to zero. A nonzero `preview_rc` still describes a preview, never a successful backup. The script's real payloads currently omit preview markers, and that absence remains allowed for real results.

Only validated real success can set `outcome: success`, which enables the final `mqtt.publish` action. Notification switches and handled delivery errors do not suppress that existing success-only command. The command remains `run_pbs_verify_and_gc`, shown on the generic `proxmox/pbs/commands` topic, with QoS 0 and retain=false. This automation requests your existing listener to act; it does not implement or confirm those jobs.

A shared notification sequence formats all three outcomes so the same switches and JSON behavior apply consistently. Handled notification errors use `continue_on_error` to let remaining channels, multipart pushes and any eligible maintenance request proceed. Home Assistant still records errors, and invalid configuration is not suppressed. Queued mode retains the previous maximum of 10 active/queued runs.

Implementation follows Home Assistant's [MQTT trigger syntax](https://www.home-assistant.io/docs/automation/trigger/#mqtt-trigger), [JSON serialization filter](https://www.home-assistant.io/template-functions/to_json/), [script variables, if/choose/repeat and error handling](https://www.home-assistant.io/docs/scripts/), and [queued mode](https://www.home-assistant.io/docs/automation/modes/).

## Verification and target-host checks

Offline checks cover all 256 combinations of the eight notification switches across three outcomes, actual publisher payloads, malformed/manual events, full JSON recovery and types, oversized/escaped Unicode payloads, Pushover lengths and success-only maintenance. See the project VERIFICATION.md for final results.

Testing used PyYAML 6.0.3 and Jinja2 3.1.6 with strict undefined handling and native values. The Home Assistant `to_json` filter was represented locally using standard JSON serialization; choose/if/repeat action flow and handled service errors were simulated without making service calls. This does not replace validation/execution in Home Assistant's own template/action engine.

On your installation, confirm the MQTT integration is connected to the script's broker, `notify.pushover` exists and the datastore listener consumes the existing command topic. Save the automation and run the script in dry-run mode with MQTT enabled. Its trace should select the dry-run branch and you should receive whichever preview channels you enabled, with JSON if enabled. Use the script-generated MQTT event for this test; Home Assistant's manual Run actions does not supply a real MQTT trigger.

If the base topic already contains a retained success from an older configuration, that old result can be replayed when Home Assistant subscribes/reconnects. Setting retain=false does not remove an existing retained message. Remove any stale retained backup result on the broker before enabling this maintenance-triggering automation. There is no durable duplicate-event suppression in the original script payload or this automation, so a duplicate valid success can request maintenance again.

No live Home Assistant, Pushover, MQTT delivery, Proxmox/PBS backup or downstream verify/GC listener was tested here. Live delivery and downstream job completion remain to be checked on your system.
