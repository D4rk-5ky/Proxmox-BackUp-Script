# Release verification — 0.0.5

This release advances exactly one patch step from verified 0.0.4. The existing application, tests, configuration and project documentation were reviewed before the refactor. All previous file paths remain; the original launcher now delegates to the adjacent pbs_backup package.

## Local checks

- **48 offline regression tests pass on Python 3.12.14 and Python 3.9.6**, including all 46 existing tests adapted to module imports and module-scoped mocks. Python 3.12 uses tomllib; Python 3.9 uses genuine Tomli 2.4.1 from the locally bundled pip vendor directory through test-only PYTHONPATH. No vendored dependency is packaged.
- Two additional tests exercise the actual launcher from an unrelated working directory and through a symlink, and import every module in a fresh process while blocking subprocess/directory creation. Help/version work and missing private config fails safely with the correct script-adjacent path. Imports create no logs or backup commands.
- All Python sources compile in memory, including the launcher, all six package files and tests. CLI help/version also work with site-packages disabled (`python -B -S`) and without reading config. Bash example syntax passes.
- AST comparisons confirm all 17 top-level functions are retained. Sixteen bodies match exactly; main matches after normalizing only its three module-qualified notification references. All three nested functions/callbacks remain. Version metadata and package-parent path anchoring are checked separately.
- The config examples, .gitignore, dependencies and legal file are byte-for-byte unchanged from 0.0.4. All 30 operational options remain documented/commented; all 35 CLI spellings and all 20 application functions/callbacks plus every test helper/method are covered in the code map. Original disclaimer text remains verbatim in README.
- Existing tests preserve selection safeguards, defaults, root/tool/Paho checks, silent/partial/closed-pipe deadlines, error-only .err, script-local logs, CLI precedence and TOML validation. All four dry-run notification combinations, independent failures, real-run behavior, preview MQTT routing/retention/payload and sendmail validation/submission remain covered without sending notifications.
- 32 Git path cases pass in an isolated temporary repository. Actual staging includes every new package module and the root config.example.toml, while excluding private configs and the retained legacy examples. No user's repository was staged or changed.
- Version metadata, VERSION, cumulative change record and archive agree on 0.0.5; the next release is 0.0.6. Rollover remains 0.0.99 → 0.1.0. README documents full-directory installation and preserving private settings.

## Archive and provenance checks

The final ZIP contains **22 files**: all 16 prior-release paths plus pbs_backup/__init__.py, app.py, backup.py, cli.py, logging_utils.py and notifications.py. Both original paths (README.md and pbs-backup) remain. Existing files are updated where needed; no original or previous path is removed.

The 0.0.4 archive SHA-256 was recomputed and its contents matched the preserved source byte-for-byte. Both preserved original extracted files were rehashed against the recorded original manifest. The original Downloads ZIP is unavailable, so its historical whole-archive hash cannot be recomputed; original-content verification uses the preserved extracted files and recorded hashes.

The ZIP is CRC-checked, compared byte-for-byte to the full release directory, checked for safe relative paths and extracted for final checks. Every internal manifest hash is verified and the executable launcher mode is preserved. Compilation, CLI/config/documentation checks, Git rules and both Python regression suites are repeated against the extracted deliverable. No configured config.toml, credentials, runtime logs, bytecode, caches, virtual environment, OS metadata, build output or temporary files are packaged.

ORIGINAL_MANIFEST.json records source provenance. PREVIOUS_RELEASE_MANIFEST.json records every prior file digest and update status plus the prior ZIP digest. RELEASE_MANIFEST.sha256 covers all files except itself to avoid a circular hash; the ZIP .sha256 sidecar covers the whole archive. Checksums verify integrity, not signatures.

## Limits

No live Proxmox VE/PBS host, MQTT broker or mail service was contacted. Actual backups/restores, guest interruption/migration, storage permissions/retention, live broker TLS/authentication/QoS/retained status and email relay/inbox delivery need target-host checks. Subprocess tests use harmless local Python children and notification boundaries are mocked.

Existing behavior remains: error classification recognizes explicit severity prefixes, with unlabelled diagnostics kept in the full log. A backup timeout kills/reaps only the direct subprocess, so PVE workers can continue. MQTT publication timeout does not bound DNS/connection setup. Real-backup MQTT failure preserves the backup exit code. Successful sendmail submission means local acceptance, not confirmed inbox delivery. Config validation precedes log initialization. Disk exhaustion, blocked kernel I/O and full process-tree interruption were not validated.

The application now requires the launcher and its pbs_backup directory to be deployed together. Individual modules are not standalone commands. The standard import path used by supported normal Python invocation was tested; isolated/custom Python import modes are not an additional supported deployment interface.
