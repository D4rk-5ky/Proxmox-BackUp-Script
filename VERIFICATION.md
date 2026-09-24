# Release verification — 0.0.4

This release advances one patch step from verified 0.0.3. The existing source, tests, configuration, documentation and manifests were inspected before edits. No original or prior-release file path is removed. This release adds `.gitignore` and `config.example.toml`.

## Verified locally

- All **46 offline regression tests pass on Python 3.12.14 and Python 3.9.6**. Python 3.12 uses standard-library tomllib; Python 3.9 uses genuine Tomli 2.4.1 from the local runtime's pip vendor directory through test-only PYTHONPATH. No vendored dependencies are packaged.
- In-memory compilation, CLI help/version, safe missing-config failure, and Bash syntax checks pass. No bytecode/cache is generated in the project.
- All 30 operational settings exist in the categorized template with comments; all 35 CLI spellings and every application/test function are documented. Original legal/vibe-coding text is unchanged in LEGAL.md and preserved verbatim in README.
- Uppercase, lowercase and mixed-case category names resolve identically. Duplicate category spellings and incorrectly cased option keys fail validation. Missing private config.toml never falls back to either template. A configured no-flags dry-run from another working directory creates script-local logs without backup or notification side effects.
- Existing tests cover error-only .err output, deadlines for silent/partial/closed-pipe children, selection safeguards, preflight requirements, real-backup return codes, mocked MQTT handling, and all four dry-run notification combinations. Both preview channels remain independently opt-in and cannot launch a backup.
- In an isolated temporary Git repository, 26 allowed/ignored path cases pass, including config names at multiple depths, case variants, non-TOML formats, backup copies, legacy templates, logs and caches. Actual staging with `git add .` includes only .gitignore and the root config.example.toml among the populated sample files; private configs and old examples remain ignored. No user's repository was staged or changed.
- The version in the app, VERSION, change record and archive agrees on 0.0.4; next is 0.0.5. Rollover remains 0.0.99 → 0.1.0.

## Archive verification and provenance

The final ZIP contains 16 files: all 14 previous-release paths plus .gitignore and config.example.toml. It retains both original paths, README.md and pbs-backup. The prior 0.0.3 ZIP SHA-256 was recomputed and its contents matched the preserved source byte-for-byte. Both preserved original extracted files were rehashed and matched ORIGINAL_MANIFEST.json. The original Downloads ZIP is no longer available, so its historical recorded archive hash could not be independently recomputed this release; original-content verification uses the preserved extracted files and their recorded hashes.

The ZIP is CRC-checked, checked against original/prior manifests, safely extracted, and compared byte-for-byte with the release directory. All internal SHA-256 entries are checked; the executable script mode is preserved. Compilation, CLI/config/documentation/Git checks and the offline regression suite are repeated against the extracted deliverable. LEGAL.md and requirements.txt are unchanged. No private config.toml, credentials, runtime logs, bytecode, caches, virtual environments, OS metadata, build output or temporary files are packaged.

ORIGINAL_MANIFEST.json records original provenance. PREVIOUS_RELEASE_MANIFEST.json records each previous file's digest/change status and the prior archive digest. RELEASE_MANIFEST.sha256 covers every packaged file except itself, avoiding a circular hash. The separate ZIP .sha256 covers the entire archive. These are integrity checks, not signatures. Git ignore rules govern untracked files; they do not erase history, untrack existing files or prevent a forced add.

## Not tested live

No Proxmox VE/PBS host, MQTT broker or real mail service was contacted. Actual backup/restore, host storage/retention, guest disruption, live MQTT/TLS/authentication/QoS/retained behavior and email relay/inbox delivery need target-host testing. External notification boundaries are mocked; harmless local Python children exercise stream/deadline handling.

Known behavior is preserved: error classification uses explicit severity prefixes; unlabelled child diagnostics remain in the full log. Backup timeout kills/reaps only the direct child, so PVE workers can continue. MQTT publish timeout does not bound DNS/connection setup. Real-backup MQTT failure preserves the child exit code. Sendmail success means local acceptance, not inbox delivery. Config errors precede log initialization. Disk exhaustion, blocked kernel I/O and full process-tree interruption were not validated.
