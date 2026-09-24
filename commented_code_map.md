# Commented code map

This map explains the current application, every function, and the commands used to operate or verify it. Release history lives in `VERSIONING.md`; usage and every flag/default are in `README.md`.

## Files and flow

- `pbs-backup`: the executable Python app; existing helpers remain in the original single module.
- `README.md`: installation, complete flag reference, examples, results, and operational limits.
- `pbs-backup.toml`: automatic, fully commented configuration for all 30 runtime settings.
- `config.example.sh`: optional Bash argument overrides; sourcing runs no backup, and TOML still loads.
- `requirements.txt`: Paho dependency plus conditional Tomli on Python older than 3.11.
- `VERSION` and `VERSIONING.md`: current version and cumulative change record/rollover policy.
- `LEGAL.md`: the original disclaimers and permission/no-warranty text.
- `tests/test_pbs_backup.py`: isolated regression checks using standard-library unittest/mocks and harmless Python children.
- `VERIFICATION.md`, `ORIGINAL_MANIFEST.json`, `PREVIOUS_RELEASE_MANIFEST.json`, and `RELEASE_MANIFEST.sha256`: verification limits and source/release file accounting.

The entry point calls `main` and raises `SystemExit` with its return code. `main` loads/validates TOML and optional CLI overrides, prepares script-local logs, checks root/tools/Paho, resolves guest selection, builds argv, runs or previews the backup, and publishes normal status after real runs or explicitly labelled preview notifications when opted in during dry-run. Actual backup exit codes are preserved on MQTT failure; a requested dry-run notification failure returns 3.

The optional Paho import preserves the original behavior of setting `mqtt = None` on an import failure. Help/version work anyway; normal execution and dry-run refuse to proceed without Paho. `__version__` is used by `--version` and kept equal to `VERSION`.

## Every application function

| Function | What it does | Why it exists / important behavior |
| --- | --- | --- |
| `is_root()` | Checks effective Unix UID against zero. | Keeps the original privilege gate before any backup/preview. |
| `now_iso()` | Formats local wall-clock time to seconds. | Human-readable log/payload timestamps; no timezone offset is attached. |
| `ensure_dir(path)` | Creates a directory recursively if needed. | Prepares log destinations without deleting existing content. |
| `nonempty_file(path)` | Checks existence/size, returning false on `OSError`. | Decides whether MQTT should include `err_file`; it does not detect backup errors. |
| `build_log_paths(log_dir, prefix)` | Builds paired `.log`/`.err` names using local time, microseconds, and PID. | Distinguishes concurrent runs; paths share one identifier. |
| `setup_logger(logfile, errfile)` | Closes prior handlers and configures stdout, full file, and delayed ERROR+ file handlers. | Repeated invocations use the correct paths. Wrapper INFO/WARN stays out of `.err`; ERROR/CRITICAL is included. |
| `run_command_stream(cmd, logger, logfile, errfile, timeout, dry_run)` | Previews or runs argv without a shell, capturing combined stdout/stderr into the full log and filtering explicit child error lines into `.err`. | Uses selectors, incremental UTF-8 decoding and monotonic deadlines to handle silence, partial output, and exit waiting. Returns child rc or 255 for caught launch/stream failures. A nonzero exit generates an error summary. Nested finally blocks protect pipe closure and direct-child kill/reaping even if final error flushing fails. Use the logger configured by `setup_logger` to capture wrapper errors. |
| `mqtt_publish(...)` | Creates a Paho MQTT 3.1.1 client (v2 callbacks, falling back to older construction), applies auth/TLS, connects, starts its network loop, serializes JSON, publishes, and waits for completion. | Centralizes MQTT behavior. Verified TLS remains default when TLS is enabled. Disconnect/loop cleanup occurs in `finally` after the loop starts. Publish errors propagate to `main`; connection time is not bounded by `--mqtt-timeout`. |
| `mqtt_publish.on_publish(...)` | Marks callback completion and logs message ID. | Allows callback completion to complement `is_published()` checking across supported Paho APIs; QoS 0 completion is local send only. |
| `mqtt_publish.on_disconnect(...)` | Extracts/logs the reason using either v1 or v2 argument layout. | Avoids mistaking v2 disconnect flags for the reason code. |
| `publish_backup_status(..., dry_run=False)` | Builds the existing normal payload, or an explicitly labelled dry-run payload with rc=null, dry_run=true, backup_executed=false, and preview_rc. Calls the same mqtt_publish function. | Previews append `/dry-run` to the topic and force non-retained publication to protect the real backup status. Real-run fields and routing stay unchanged. |
| `resolve_selection(args)` | Removes explicitly excluded IDs and, when requested, queries Proxmox guest inventory and intersects selection with local running QEMU/LXC guests. Mutates `args` to contain the resolved selection. | Proxmox does not accept `--exclude` with explicit VMIDs or a `--only-running` option. Resolving these before command construction preserves the intended selection. No guests remaining is an error, never a fallback to all. Query errors are handled by `main` as preflight failures. |
| `build_vzdump_cmd(args)` | Builds one argv list from resolved selection, storage, backup settings, and optional mail arguments. | Reuses the original command builder and never invokes a shell. Explicit selections send `--all 0`; all-guest exclusions are one comma-separated value. MQTT/log/timeout controls stay in the wrapper. Call `resolve_selection` first. |
| `parse_args()` | Defines existing CLI controls, obtains the config path, merges validated TOML defaults, reapplies explicit CLI values, normalizes IDs/paths, and checks option relationships. | Reuses the original parser as the single source for operational types/defaults/choices. Precedence is CLI > TOML > built-ins. Help/version exit before config access. Invalid selection, ports, timeouts, TLS/password combinations, topics, and paths fail before a backup. |
| `main()` | Loads config/options, initializes logs, checks prerequisites/selection, builds/runs or previews the command, then attempts appropriate notifications. | Never executes a dry-run backup. Both preview channels are opt-in and independently attempted; failures enter .err and return 3 for dry-run. Real-run email remains with vzdump, and MQTT failure preserves its backup exit code. |
| `is_error_line(line)` | Tests explicit ERROR/TASK ERROR/FATAL/CRITICAL prefixes, optionally following numeric guest IDs and timestamps. | Prevents ordinary stderr, INFO/WARN, or incidental error words from being misclassified. Unlabelled diagnostics stay in the full log. |
| `run_command_stream.filter_errors(output, final)` | Buffers partial lines between decoded chunks, writes only recognized errors, and flushes a final fragment. | Error prefixes split across reads are recognized; successful/progress messages never get copied wholesale to `.err`. |
| `load_config(path, parser)` | Reads TOML through tomllib/Tomli; checks known tables/keys and exact types using the parser actions. Converts optional empty strings and timeout 0, and anchors TOML CA paths to the config directory. | Rejects typos/invalid settings instead of silently dropping them. Syntax errors omit source excerpts to avoid exposing password values. Returns defaults for the existing parser rather than duplicating backup/MQTT execution code. |
| `dry_run_recipients(value)` | Parses comma-separated bare ASCII email addresses or simple local aliases and rejects missing recipients, malformed addresses, leading command options, and control/header injection. | Reused by dry-run configuration validation and email submission. Does not change real-backup recipient handling or resolve PVE user IDs. |
| `send_dry_run_email(...)` | Builds EmailMessage headers/body explicitly stating DRY-RUN and NO BACKUP EXECUTED; submits through local sendmail with a 30-second timeout. | Gives previews a mail path without invoking vzdump. Includes only planned command/host/storage/log paths; successful submission means local mail-service acceptance, not inbox delivery. |

`SCRIPT_DIR` resolves the real script file. `CONFIG_SECTIONS` maps TOML keys to parser destinations (MQTT drops the repeated `mqtt_` prefix). `ERROR_LINE` defines recognized severity prefixes. Python 3.11+ uses `tomllib`; 3.9/3.10 uses `tomli`. Absence of both is allowed for help/version but blocks normal startup.

## App commands and option routing

No external command is executed through a shell. `shlex.quote` creates readable logs only; execution uses argv lists.

| Command / wrapper flags | What executes and why |
| --- | --- |
| `pbs-backup` with no flags | Loads adjacent `pbs-backup.toml`, creates the configured script-relative logs directory, and follows its dry-run/backup setting. |
| `--config PATH` | Selects another TOML file; a relative path uses the working directory. It does not move the default logs directory. |
| `pbs-backup -h` / `--help` | Argparse displays command usage and exits. |
| `pbs-backup --version` | Argparse prints the current version and exits. |
| `--all` | Produces `vzdump --all ...`, selecting all guests on the node. |
| `--no-all --vmid 100 101` | Produces `vzdump 100 101 --all 0 ...`, pinning the selection instead of inheriting all-guest mode. |
| `--exclude 101 105` with all guests | Adds `--exclude 101,105` once. |
| `--exclude ...` with explicit IDs | Subtracts IDs in `resolve_selection`; no conflicting exclusion option reaches `vzdump`. |
| `--only-running` | Executes `pvesh get /cluster/resources --type vm --output-format json` with `check=True`, captured output, and a 30-second timeout. Filters `node`, `type`, `status`, and `vmid`; emits an explicit selection. The local node is the first component of `os.uname().nodename`. No inventory mutation occurs. |
| `--storage`, `--mode`, `--compress`, `--bwlimit` | Always become their corresponding `vzdump` options, including the wrapper's default values. |
| `--notes-template`, `--mailto`, `--mailnotification` | Passed as literal value pairs when supplied. Installed PVE governs support/notification behavior. |
| `--quiet` | Adds `vzdump --quiet 1`; does not silence wrapper logs. |
| `--timeout` | Controls wrapper deadline/kill of its direct child; no `vzdump --timeout` is emitted. |
| `--dry-run` | Logs the resolved command without starting vzdump. Default notifications are off; explicit preview opt-ins allow the dedicated notification paths. Log creation, preflight and optional inventory queries still occur. |
| `--dry-run-mqtt` | During dry-run only, reuse MQTT publication with a labelled payload, `/dry-run` topic suffix, and retain=false. Uses existing connection options; default off. |
| `--dry-run-email` | During dry-run only, submit the labelled test email to mailto independently of mailnotification. Default off; does not cause extra email during real backups. |
| `sendmail -i -t` | Read the serialized message from stdin, take validated recipients from To headers, and ignore a dot-only line as a terminator. No shell or backup command is executed; MTA routing is configured on the host. |
| `--log-dir`, `--log-prefix` | Control local log paths; relative directories are script-relative and default to `logs/`. Never passed to `vzdump`. |
| `--mqtt-host`, `--mqtt-port`, `--mqtt-topic` | Supply broker connection and destination topic to Paho. |
| `--mqtt-user`, `--mqtt-pass` | Configure Paho username/password; require a username when a password is provided. |
| `--mqtt-qos`, `--mqtt-retain` | Select publish quality of service and retained-message behavior. |
| `--mqtt-timeout`, `--mqtt-client-id` | Control publish-completion wait and client identity. Connection establishment has its own library behavior. |
| `--mqtt-tls`, `--mqtt-cafile`, `--mqtt-insecure` | Enable TLS, optionally choose trust roots, and explicitly opt out of hostname checking. The latter two require TLS. |

The script does not expose `vzdump` passthrough arguments, restore commands, or retention switches. Host defaults for unexposed options continue to apply.

## Supporting shell commands

| Command | What it does and why |
| --- | --- |
| `sudo apt-get install python3-paho-mqtt` | Installs the host distribution's MQTT Python package for the application. |
| `chmod +x pbs-backup` | Marks the original script executable for `./pbs-backup` invocation. |
| `python3 pbs-backup ...` | Runs the same app using an explicitly selected Python interpreter. |
| `sudo ./pbs-backup ...` | Executes the app as root, satisfying the existing privilege requirement. |
| `source ./config.example.sh` | Loads optional `PBS_BACKUP_ARGS` CLI overrides in Bash; no backup is run and TOML remains the default workflow. |
| `sudo ./pbs-backup "${PBS_BACKUP_ARGS[@]}"` | Expands the array as separately quoted overrides; TOML loads first and the example forces dry-run. |
| `python3 -B -m unittest discover -s tests -v` | Discovers and runs the offline test suite, prints each result, and suppresses bytecode caches. |
| `bash -n config.example.sh` | Parses the Bash example without executing it. |
| `sha256sum -c RELEASE_MANIFEST.sha256` | On Linux, checks each listed packaged file against its SHA-256 digest. The manifest excludes itself to avoid a circular checksum. |
| `chmod 600 pbs-backup.toml` | Restricts config access to its owner before storing plaintext credentials. |
| `python -m pip install -r requirements.txt` | Installs Paho and conditional Tomli in a selected virtual environment; does not change app settings. |
| `sudo /path/to/venv/bin/python ./pbs-backup` | Runs the same TOML-driven app with the selected environment and root privileges. |

## TOML-to-parser setting map

Every key below maps to the existing execution path in the command-routing table; the README and TOML comments explain values/defaults. There are no TOML keys for help, version, or choosing the config itself.

| TOML key | Parser destination / operational route |
| --- | --- |
| `selection.all` | `all` / `--all` |
| `selection.vmid` | `vmid` / `--vmid` |
| `selection.exclude` | `exclude` / `--exclude` |
| `backup.storage` | `storage` / `--storage` |
| `backup.mode` | `mode` / `--mode` |
| `backup.compress` | `compress` / `--compress` |
| `backup.bwlimit` | `bwlimit` / `--bwlimit` |
| `backup.only_running` | `only_running` / `--only-running` |
| `backup.quiet` | `quiet` / `--quiet` |
| `backup.timeout` | `timeout` / `--timeout` |
| `backup.notes_template` | `notes_template` / `--notes-template` |
| `backup.dry_run` | `dry_run` / `--dry-run` |
| `backup.dry_run_mqtt` | `dry_run_mqtt` / `--dry-run-mqtt` |
| `backup.dry_run_email` | `dry_run_email` / `--dry-run-email` |
| `mail.mailto` | `mailto` / `--mailto` |
| `mail.mailnotification` | `mailnotification` / `--mailnotification` |
| `logging.log_dir` | `log_dir` / `--log-dir` |
| `logging.log_prefix` | `log_prefix` / `--log-prefix` |
| `mqtt.host` | `mqtt_host` / `--mqtt-host` |
| `mqtt.port` | `mqtt_port` / `--mqtt-port` |
| `mqtt.topic` | `mqtt_topic` / `--mqtt-topic` |
| `mqtt.user` | `mqtt_user` / `--mqtt-user` |
| `mqtt.pass` | `mqtt_pass` / `--mqtt-pass` |
| `mqtt.qos` | `mqtt_qos` / `--mqtt-qos` |
| `mqtt.retain` | `mqtt_retain` / `--mqtt-retain` |
| `mqtt.timeout` | `mqtt_timeout` / `--mqtt-timeout` |
| `mqtt.client_id` | `mqtt_client_id` / `--mqtt-client-id` |
| `mqtt.tls` | `mqtt_tls` / `--mqtt-tls` |
| `mqtt.cafile` | `mqtt_cafile` / `--mqtt-cafile` |
| `mqtt.insecure` | `mqtt_insecure` / `--mqtt-insecure` |

## Every test function

The test module loads the real app with `runpy` without invoking its `__main__` entry point. Shared helpers isolate temporary files and external boundaries; no test contacts a broker or starts `vzdump`.

| Function | What it checks / why |
| --- | --- |
| `BackupTests.setUp()` | Allocate private logs and a quiet logger for each isolated test. |
| `BackupTests.tearDown()` | Close app handlers so repeated main calls cannot reuse another test's log. |
| `BackupTests.args()` | Parse realistic command lines using the application's existing parser. |
| `BackupTests.run_child()` | Run a harmless Python child through the real streaming/deadline code. |
| `BackupTests.call_main()` | Mock external boundaries while retaining parsing and main orchestration. |
| `BackupTests.test_original_defaults()` | Keep all guests, snapshot, zstd, unlimited bandwidth, and MQTT defaults. |
| `BackupTests.test_invalid_input_rejected()` | Reject inputs that could broaden selection or silently disable safeguards. |
| `BackupTests.test_explicit_exclusions()` | Subtract exclusions locally; never send conflicting VMIDs and --exclude. |
| `BackupTests.test_empty_selection_refused()` | Removing the last explicitly selected guest must not fall back to all. |
| `BackupTests.test_all_exclusions_single_list()` | Forward every excluded guest as one Proxmox VMID-list value. |
| `BackupTests.test_running_selection()` | Use only local running QEMU/LXC guests and respect explicit filters. |
| `BackupTests.test_running_query_failures()` | Missing tools, invalid inventory, and query failures cannot trigger backups. |
| `BackupTests.test_literal_arguments()` | Keep notes as a single argv value, without shell interpolation. |
| `BackupTests.test_streams_and_exit_status()` | Keep both streams in the full log and only errors/failure summary in .err. |
| `BackupTests.test_silent_timeout()` | Enforce the deadline even when the child never emits a newline. |
| `BackupTests.test_partial_line_timeout()` | A flushed fragment without newline cannot block deadline enforcement. |
| `BackupTests.test_closed_pipe_timeout()` | Apply the same deadline to a child that closes its output then sleeps. |
| `BackupTests.test_invalid_output_bytes()` | Undecodable output must not discard the child result or abort logging. |
| `BackupTests.test_launch_failure_returns_error()` | A missing executable produces rc=255 so main can publish failure. |
| `BackupTests.test_dry_run_never_launches_child()` | The streaming helper's dry-run branch must not spawn any process. |
| `BackupTests.test_main_dry_run_never_publishes()` | A default preview sends no MQTT without the new explicit opt-in. |
| `BackupTests.test_preflight_guards()` | Root, vzdump, and Paho checks remain mandatory, even for previews. |
| `BackupTests.test_no_guests_main()` | Main converts an empty resolved selection into a preflight failure. |
| `BackupTests.test_backup_results_and_mqtt_failure()` | Publish actual run results; preserve backup exit status if MQTT fails. |
| `BackupTests.test_payload_mapping()` | Status derives from rc and err_file reflects file content, not success. |
| `BackupTests.test_mqtt_publish_cleanup()` | Both Paho API paths configure TLS/auth and clean up after publish or timeout. |
| `BackupTests.config_args()` | Parse TOML without required CLI settings to exercise config-first usage. |
| `BackupTests.valid_config()` | Provide minimal configured destinations, leaving other settings at defaults. |
| `BackupTests.test_config_only_and_precedence()` | Use TOML alone and let an explicit CLI value override it without losing others. |
| `BackupTests.test_config_all_options()` | Load all shipped keys and correctly convert unset strings, arrays and timeout. |
| `BackupTests.test_config_invalid_types_keys_and_choices()` | Reject TOML typos, invalid choices and bool/integer confusion before running. |
| `BackupTests.test_config_syntax_and_secret_not_echoed()` | Syntax errors and invalid password types must not dump secret-bearing values. |
| `BackupTests.test_missing_config_and_missing_parser()` | Fail closed for unreadable config or unavailable TOML support; no fallback run. |
| `BackupTests.test_help_and_version_without_config()` | Inspection commands work even if TOML/Paho/config files are unavailable. |
| `BackupTests.test_config_relative_paths()` | Anchor TOML CA paths to config and log paths to script, independent of cwd. |
| `BackupTests.test_no_flags_creates_script_local_logs()` | Run a configured preview from another cwd without backup/MQTT side effects. |
| `BackupTests.test_success_keeps_error_log_empty()` | INFO/WARN on stderr and incidental error words are not error messages. |
| `BackupTests.test_error_severity_prefixes()` | Recognize explicit error levels, including guest/timestamp and TASK prefixes. |
| `BackupTests.test_split_error_line_and_final_fragment()` | Error filtering survives chunk splits and an error without a final newline. |
| `BackupTests.test_wrapper_errors_and_logger_reinitialization()` | Separate wrapper errors from INFO/WARN and switch paths between runs. |
| `BackupTests.test_preflight_and_mqtt_errors_written()` | Capture runtime preflight/MQTT failures in .err without progress noise. |
| `BackupTests.run_notifications()` | Run the real dry-run path with notification boundaries mocked and no child allowed. |
| `BackupTests.test_dry_run_notification_matrix()` | All four opt-in combinations leave backup execution disabled and send only requested channels. |
| `BackupTests.test_notification_failures_attempt_other_channel()` | Requested notification failures return 3, log errors, and do not skip the other channel. |
| `BackupTests.test_real_backup_ignores_preview_options()` | Real runs keep normal MQTT and vzdump email behavior with no extra test email. |
| `BackupTests.test_preview_mqtt_payload_and_routing()` | Preview payload cannot look like backup success or replace retained real status. |
| `BackupTests.test_dry_run_email_recipient_validation()` | Reject missing, malformed and header-injected test recipients before notifications. |
| `BackupTests.test_email_message_and_submission()` | Build an explicit preview email and send it via bounded stdin, not a backup subprocess. |
| `BackupTests.test_email_transport_failures()` | Surface missing sendmail, submission failure, and timeout without real delivery. |
| `BackupTests.test_notification_config_types_and_cli()` | Preview options are strict TOML booleans, default off, and explicitly overridable. |

`unittest.main()` runs the class directly; discovery finds it too. Tests mock MQTT and sendmail and use temporary Python children for streaming/deadlines. No backup or real notification is sent.
