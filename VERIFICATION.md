# Release verification — 0.0.3

The full original project and the prior release were inspected before edits. This release advances exactly one patch step from 0.0.2. The original input and previous ZIP remain untouched.

## Local checks

- **42 offline regression tests pass on Python 3.12.14** using standard-library `tomllib`.
- **The same 42 tests pass on Python 3.9.6** using Tomli 2.4.1 from the locally bundled pip vendor directory, supplied only through the test process's `PYTHONPATH`. No vendored dependency is included in the project. The fallback was tested with the locally available genuine Tomli parser.
- Python in-memory compilation passes for the app and test module without generating `.pyc` files.
- CLI help/version work without config/Paho/TOML support; missing config, invalid syntax, bad types/choices/keys, and missing destinations fail before any backup. Error diagnostics do not echo secret-bearing TOML excerpts.
- The complete shipped TOML parses, contains all **30 operational options**, and comments every value. Required destinations are deliberately empty and dry-run is enabled for initial setup.
- Config-only startup, optional CLI precedence, relative path rules, and startup from a different working directory are covered. A configured default no-flags preview creates `logs/` beside the script and invokes neither a backup nor notifications.
- Success output, INFO/WARN on stderr, and incidental error words stay out of `.err`. Explicit error prefixes, split chunks/final fragments, command failure summaries, runtime preflight, and MQTT failures enter `.err`; full output remains in `.log`.
- Silent/partial/closed-pipe subprocess deadlines, launch failures, exclusion/running-guest selection, original defaults/preflight gates, dry-run isolation, payload mapping, and mocked Paho v1/v2 cleanup remain covered.
- Documentation coverage checks verify **35 CLI spellings**, **30 TOML keys**, **20 application functions** including nested callbacks, and every test helper/method. Original legal/vibe-coding notices are present verbatim in both `LEGAL.md` and README.
- Bash syntax and the retained override example are checked. Version, archive name and change record agree on 0.0.3; the next version is 0.0.4, with 99 → next minor's 0 rollover.

- All four dry-run notification combinations are tested with the actual preview execution path and mocked mail/MQTT boundaries. None may launch a backup. Real runs ignore preview options and do not send an extra test email.
- Preview MQTT topic suffix, forced non-retention, explicit dry-run status, null backup rc, additional preview markers, existing connection options, and exclusion of credentials from payload are checked.
- Email tests inspect MIME/header/body construction and bounded stdin submission to sendmail. Missing mail service, nonzero submission result, timeout, invalid recipients, and CR/LF/NUL/header injection are covered without sending mail.
- Independent notification failure handling attempts both requested channels, logs failures in .err, and returns 3 for dry-run. Default silence, normal backup return-code behavior, and preflight gates remain covered.

## Archive checks

The ZIP is reopened, CRC-checked, compared byte-for-byte to the complete release directory, and checked against both the original source archive and 0.0.2. Both original files and all 14 prior-release file paths remain. This release contains 14 files, with no added or removed paths relative to 0.0.2. Existing application/config/documentation/test/manifest files are updated as required. `LEGAL.md` and `requirements.txt` remain unchanged.

The archive is safely extracted and rechecked with compilation, help/version, TOML loading, and the regression suite. The script's executable mode is recorded in the ZIP. No runtime logs, configured credentials, bytecode, caches, temporary files, OS metadata, virtual environments, or build output are packaged.

`ORIGINAL_MANIFEST.json` records original paths and SHA-256 values. `PREVIOUS_RELEASE_MANIFEST.json` records the 0.0.2 ZIP hash and each prior file's hash/change status. `RELEASE_MANIFEST.sha256` hashes every packaged file except itself to avoid circular hashing. The ZIP's separate `.sha256` file covers the whole archive. Checksums are integrity checks, not signatures.

## What was not tested live

No Proxmox VE/PBS host, MQTT broker, or real mail service was contacted. No real notification was sent. Actual backups/restores, PBS/storage permissions, host retention settings, guest disruption/migration, PVE email delivery, local sendmail relay/queue/inbox delivery, live Paho/TLS/authentication/QoS/retained status, and cross-version Proxmox integration still need testing on the target host.

The error filter uses known severity prefixes, not arbitrary language inference. Unlabelled child diagnostics/continuation lines stay in `.log`; a nonzero child exit also creates a failure summary in `.err`. Future Proxmox output-format changes may require extending the recognized prefixes.

Timeout cleanup still targets only the direct subprocess, not all Proxmox workers. MQTT connection setup is not bounded by the publish timeout, and MQTT failure deliberately preserves the backup exit code. Disk exhaustion, blocked kernel I/O, full process-tree interruption, and restore integrity were not validated.

A successful sendmail invocation confirms local submission only; it does not prove inbox delivery or test the full PVE notification system. A timed-out submission may have partially progressed; no automatic retry is performed. MQTT preview tests are mocked and do not validate live broker permissions for the `/dry-run` topic.

Config errors happen before log initialization and therefore print to terminal stderr. Logging initialization failures stop execution. Runtime failures can prevent final MQTT delivery. The app does not manage schedules, log rotation, guest locks, or restore validation.
