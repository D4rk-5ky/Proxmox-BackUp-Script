# Versioning and complete change record

This is the canonical versioning.md document, named `VERSIONING.md`. Keep history here; `README.md` describes current usage only.

## Release rules

Every created release advances exactly one patch step. Starting with `major.minor.patch`, increment patch by one while it is below 99. At 99, increment minor and reset patch to zero: **0.0.99 → 0.1.0**, never 0.0.100. The current release is 0.0.4; the next release is 0.0.5. Keep `VERSION`, `pbs-backup.__version__`, this record, verification, and ZIP name consistent. Update CLI/config examples and the code map for every changed option/function. Do not create intermediate numbered releases for working edits.

## 0.0.4 — 2026-09-24

- Add `config.example.toml` with all 30 settings and comments grouped into `[SELECTION]`, `[BACKUP]`, `[MAIL]`, `[LOGGING]`, and `[MQTT]`. Make private `config.toml` beside the real script the default; missing configuration fails with copy/edit guidance instead of using the example or a fallback. Existing files remain usable via `--config`.
- Reuse `load_config` to accept category names case-insensitively while keeping keys strict. Reject categories repeated with different casing to avoid ambiguous configuration merges. Existing lowercase categories remain accepted.
- Add `.gitignore` for case-insensitive `config*.*` names at any depth and all TOML files, with only root `config.example.toml` excepted. Ignore logs, bytecode, build caches, virtual environments and temporary files. Keep placeholder `pbs-backup.toml` and `config.example.sh` in the full ZIP; both are Git-ignored. Never package private `config.toml`.
- Document safe template copying, private config loading, every category/option, Git behavior for already tracked files, and all related commands. Update function/command maps and preserve the original vibe-coding disclaimer verbatim.
- Extend regression checks for category casing/equivalence, ambiguous duplicates, strict key casing, default-file selection and missing-file safety. Verify Git ignore rules in an isolated temporary repository. Update provenance, version and release checksums. Preserve all original and prior-release file paths.
- Keep log placement, error-only `.err`, independent opt-in dry-run MQTT/email, original backup defaults, preflight gates, TLS and timeout behavior unchanged. No new dependency. See `VERIFICATION.md` for results and live-testing limits.

## 0.0.3 — 2026-09-24

### Code changes

- Add independent `backup.dry_run_mqtt` and `backup.dry_run_email` TOML booleans and matching optional `--dry-run-mqtt`/`--dry-run-email` flags. Both default to false, are effective only during dry-run, and never enable dry-run themselves.
- Reuse `publish_backup_status` and the existing MQTT connection path for opted-in previews. Preview payloads have `status="dry-run"`, `rc=null`, `dry_run=true`, `backup_executed=false`, and `preview_rc`; real-backup payloads remain unchanged. Append `/dry-run` to the topic and force retain=false so preview publication does not overwrite the normal retained backup result.
- Add `dry_run_recipients` to validate comma-separated bare ASCII addresses or local aliases, reject missing/invalid recipients and control-character/header injection, and limit that validation to opted-in dry-run email. Normalize malformed-address exceptions across supported Python versions, including the older parser's empty-domain IndexError. Real-backup PVE mail recipient behavior is unchanged.
- Add `send_dry_run_email` using standard-library EmailMessage and the host sendmail-compatible service, found through PATH or `/usr/sbin/sendmail`. Submit via argv `-i -t` and stdin with a 30-second timeout, without shell execution or running vzdump. Subject/body state DRY-RUN and NO BACKUP EXECUTED. Include planned command and local log paths as text; do not attach config/log files or credentials. Local submission is not proof of inbox delivery.
- Reuse `mail.mailto` for preview email. Explicit dry-run email is independent of `mailnotification` and does not use PVE user-to-email resolution or notification targets. Real backup email stays with vzdump; no duplicate test email is generated during real runs.
- Attempt each requested dry-run channel independently after existing preflight/selection succeeds. Record individual outcomes, log failures to the existing .err handler, and return 3 for notification failure. Preserve preview rc if already nonzero. Keep normal backup return-code behavior unchanged when MQTT fails.
- Preserve default dry-run silence, root/vzdump/Paho gates, guest-selection checks, backup non-execution during dry-run, script-local logs, error-only .err, and existing timeout/TLS behavior. No new third-party dependency.

### Documentation and verification changes

- Update README usage, all option references, preview topic/payload, sendmail requirements, recipient limitations, outcome/exit semantics, and dry-run examples. Preserve the original vibe-coding disclaimer verbatim.
- Comment both new options in the complete TOML and retain/update the Bash override example. Update every function/command map, version record, provenance and file hashes.
- Extend offline tests for all four notification combinations, preview routing/retention/payload, unchanged real-run behavior, independent failure handling, email construction/submission, recipient validation, transport failures/timeouts, strict TOML types and optional CLI overrides.
- Package all 14 existing project files; no original or prior-release file is removed. Exclude caches, temporary files, runtime logs and configured secrets.

### Validation limits

Only isolated/mock notification tests were performed; no real email or MQTT message was sent. Live host mail routing/inbox delivery, broker behavior, and Proxmox/PBS backup/restore still need target-host checks. Exact results are in `VERIFICATION.md`.

## 0.0.2 — 2026-09-24

### Code changes

- Add automatic `pbs-backup.toml` loading beside the resolved script path and an optional `--config` selector. All 28 operational settings move into a fully commented file; existing flags remain optional overrides. Reuse the existing parser's types, choices, defaults, command builder, and safety validations.
- Add `load_config` and the `CONFIG_SECTIONS` mapping. Validate tables, unknown keys, exact boolean/integer types, lists, choices, and required values. Reject missing/unreadable/invalid config instead of falling back to a backup. Suppress syntax excerpts that might reveal credentials.
- Use standard-library `tomllib` on Python 3.11+ and optional `tomli` on Python 3.9/3.10. Add `requirements.txt`; missing TOML support produces an actionable error. Help/version still work without config or either dependency.
- Define precedence as CLI > TOML > built-in defaults. Interpret optional empty strings as unset and TOML backup timeout 0 as disabled. Resolve relative log paths beside the script and relative TOML CA paths beside the config. Config-file paths supplied on CLI are working-directory relative.
- Default logs to script-local `logs/`, created automatically. Move logger setup before runtime preflight so root/tool/guest-selection errors are saved. Abort before execution if logging initialization fails.
- Add a dedicated ERROR+ log handler for `.err`; refresh handlers on repeated in-process runs. Keep complete output in `.log` and only recognized child error-level lines in `.err`. Proxmox INFO/WARN output on stderr is not treated as an error.
- Add `is_error_line` and incremental `filter_errors` line assembly, recognizing ERROR/TASK ERROR/FATAL/CRITICAL prefixes with optional guest IDs/timestamps, split chunks, and final fragments. Preserve all other child diagnostics in `.log`. Add a nonzero-exit error summary even when child output has no explicit error label.
- Route wrapper/preflight/launch/timeout/MQTT errors through the error handler. Remove successful completion and general output from `.err`. Empty/missing error files produce `err_file: null` in MQTT.
- Add microseconds and PID to log names to distinguish concurrent runs. Protect subprocess cleanup with a nested finally even if flushing filtered error output fails.
- Preserve existing root/tool/Paho checks, backup defaults, no-MQTT dry-run behavior, subprocess timeout strategy, verified TLS, and backup-result exit semantics. The distributed TOML intentionally enables dry-run and leaves required destinations empty; users configure it before execution.

### Documentation and project changes

- Rewrite README around edit-TOML-and-run usage, all keys/defaults/optional flags, path rules, strict parsing, logging semantics, examples, exit codes, and testing limits.
- Include the complete original vibe-coding disclaimer and permission/no-warranty text directly in README while retaining `LEGAL.md` unchanged.
- Add the commented `pbs-backup.toml`; update and retain `config.example.sh` as an optional override example. Update every function/command explanation in `commented_code_map.md` and retain the prior version record.
- Expand regression checks for config-only startup, every setting, precedence, type/syntax errors, secret-safe diagnostics, path resolution, clean error logs, chunked error messages, and runtime errors. Update version, verification, provenance, and release manifests; package the full project without caches, secrets, runtime logs, or temporary files.

### Validation limits

No live Proxmox/PBS backup or restore, email delivery, or MQTT/TLS broker session is available here. See `VERIFICATION.md` for exact local results and preserved operational limits.

## 0.0.1 — 2026-09-24

Initial numbered release from the supplied, unversioned archive `Proxmox-BackUp-Script-Proxmox-BackUp-Script-Next.zip`. The source contains only `README.md` and `pbs-backup`; no earlier version is inferred.

### Code changes

- Add `__version__ = "0.0.1"`, `VERSION`, and `--version`; expand CLI flag explanations/defaults and correct storage-ID, bandwidth-unit, notes-template, MQTT/TLS, and timeout help.
- Dry-run preserves original preflight checks and logging but returns before MQTT publication; the final message states that no backup ran.
- Replace blocking line iteration with selector-driven byte reads and an incremental UTF-8 decoder. Silent output, fragments without newlines, and closed stdout no longer bypass the timeout. Invalid UTF-8 is replaced for display/logging rather than aborting the backup result.
- Use monotonic time for deadlines and backup duration. Apply the remaining deadline to subprocess exit waiting.
- Move subprocess launch inside command error handling so launch failures return 255 and reach the existing status-publication path. Always close the pipe and reap the direct subprocess, killing it if still running during cleanup. No process-group or Proxmox worker cancellation is added.
- Add `resolve_selection`, reusing the parser, existing command builder, and status flow. Explicit exclusions are applied locally; excluding every selected guest is an error. All-guest exclusions are emitted as one comma-separated `--exclude` value. Explicit commands include `--all 0` to prevent inherited all-guest selection.
- Implement `--only-running` with a read-only `pvesh get /cluster/resources --type vm --output-format json` query with a 30-second timeout. Filter local running QEMU/LXC guests and existing selections/exclusions; fail if empty or the query fails. Stop forwarding the unsupported flag to `vzdump`.
- Make `--all` and `--no-all` mutually exclusive. Reject `--vmid` with all-guest mode, missing VMIDs, empty exclusion arguments, and invalid guest IDs. Normalize numeric IDs before exclusion matching.
- Reject negative bandwidth, nonpositive timeouts, invalid MQTT ports, empty required strings, wildcard/NUL publish topics, TLS-only options without TLS, password without username, and log prefixes containing directory components. All checks precede backup execution.
- Correct MQTT disconnect reason extraction for Paho callback API v1 and v2.
- Preserve default all-guest selection, snapshot/zstd/zero-bandwidth settings, root/tool/Paho requirements, verified TLS behavior, MQTT defaults, combined `.err` logs, and backup exit status when MQTT publication fails.

### Project/documentation changes

- Rewrite README around the actual `pbs-backup` command, all flags/defaults/interactions, setup, examples, results, and current limitations; remove obsolete filename/storage/template examples and inaccurate dry-run/MQTT guarantees.
- Preserve the original disclaimer and permission/no-warranty text verbatim in `LEGAL.md` and link it from README.
- Add `config.example.sh` with every CLI option and commented alternatives; it defines a Bash array and does not execute a backup. It intentionally includes dry-run; application defaults are unchanged.
- Add `commented_code_map.md` covering every application/test function, CLI-to-command mapping, and supporting commands.
- Add 21 offline regression tests, release verification, and original-versus-release file manifests/checksums. Retain both original file paths. Package all release files without generated caches or temporary files.

### Verification limits

See `VERIFICATION.md`. No real Proxmox/PBS backup or restore, guest interruption/migration, or live MQTT/TLS delivery was tested on this macOS workspace. Only this version was created.
