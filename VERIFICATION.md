# Release verification — 0.0.6

This release advances one patch step from verified 0.0.5. The full existing project and original provenance were reviewed; no original or previous-release path is removed. The next version is 0.0.7, with patch rollover 99 to the next minor version.

## Application and documentation

- All **59 offline regression tests pass on Python 3.12.14 and 3.9.6**. Python 3.9 uses genuine Tomli 2.4.1 from the local runtime's pip vendor directory for tests only; that vendor directory is not packaged. Tests include all prior safeguards plus alias equivalence, channel/success/failure matrices, preview master switches, frozen paths, strict new settings, disabled-MQTT prerequisites and build safety/dependency/copy/cleanup behavior.
- The notification matrix covers rc 0, 7 and 255 with both MQTT switches in all combinations; mail argv covers enabled/on_success combinations. Preview tests cover independent channels, independent failure handling, non-retained normal-topic routing and explicit non-success payload markers. Vzdump mail behavior is verified through command construction and official Proxmox source inspection, not live mail delivery.
- All **10 Python sources compile in memory** (launcher, six package files, builder and two test files). Source CLI help/version and build help work without site-packages or config. Bash syntax passes. Existing tests cover real launcher/symlink behavior, selection and subprocess deadlines, strict TOML, script-local logs and error-only .err.
- All **34 TOML options** appear in both commented examples; their parsed settings match. All **44 CLI spellings** appear in README, code map and both config examples. All **22 application/build functions and callbacks**, plus test methods/helpers, are mapped. Legal text is unchanged and the complete original disclaimer remains in README.
- **39 Git path checks** and actual staging in a disposable repository confirm private config variants/TOML/logs/build environments/specs are excluded, while root config.example.toml and application/build/automation files remain available. No user repository is staged or changed.

## Native PyInstaller build

The included builder successfully creates a native macOS x86_64 onedir bundle using Python 3.12.14, PyInstaller 6.22.3, Paho 2.1.0 and Tomli 2.4.1. Archive/native-extension inspection confirms all application modules, paho.mqtt.client, TOML support, SSL and email dependencies are collected. Tomli's installed wheel uses native extensions, so its initializer is an included .so rather than a PYZ entry.

The executable passes help/version from another directory and through a symlink, missing-config safe failure, -c/--config selection and external log-path checks. A safe dry-run config with channels disabled reaches the non-root preflight guard and records only that error in .err beside the executable; nothing writes to _internal/logs or the caller's directory. No backup or live notification is executed. Build tests verify refusal to overwrite an existing bundle/private settings, dependency checks, public-file-only copying and temporary cleanup after success/failure.

This is a **macOS packaging smoke check, not Linux/PVE binary validation**. The release ZIP contains source and the builder, not a macOS binary disguised as a Proxmox build. Build on a compatible Linux architecture/system-library baseline for Proxmox. System vzdump/pvesh/sendmail remain external. The mail policy requires vzdump notification-mode support (PVE 8.1+).

## Home Assistant

**811 offline cases pass** against the anonymous included YAML: all 256 combinations of eight switches across three outcomes; actual application-publisher payloads; malformed/manual events; shared-topic preview routing; null/boolean/integer distinctions; full JSON round trips; oversized/escaped Unicode multipart Pushover messages within 1,024 characters; handled delivery failures; and real-success-only maintenance requests.

These checks use PyYAML 6.0.3 and Jinja2 3.1.6 with strict undefined/native values, a local JSON serialization equivalent for Home Assistant's to_json filter, and a simulated action interpreter. They do not run Home Assistant's actual template/action engine or contact services. Enable MQTT.on_success to receive success events and drive the success-only maintenance request; the default false intentionally suppresses those events.

## Archive and provenance

The ZIP has **27 files**: all 22 previous-release paths plus build.py, requirements-build.txt, tests/test_build.py, homeassistant/pbs-backup.yaml and homeassistant/README.md. Both original paths remain. The prior ZIP's SHA-256 is recomputed and every file is byte-compared with the preserved prior project. Both original extracted files match their recorded size and SHA-256. The original Downloads ZIP is unavailable, so its historical whole-archive hash cannot be recomputed; original content is checked using preserved files.

The final ZIP is CRC-checked, verified against the complete release directory, checked for safe unique relative paths and extracted. All internal SHA-256 entries and executable modes for pbs-backup/build.py are checked. Compilation, config/documentation checks, CLI/Bash/Git checks and both regression suites run on the extracted deliverable. The final extracted source also builds with PyInstaller for native smoke checks. No private config.toml, secrets, runtime logs, bytecode, caches, build output, virtual environment, temporary files or OS metadata is packaged.

ORIGINAL_MANIFEST.json records original provenance. PREVIOUS_RELEASE_MANIFEST.json records prior hashes and update status. RELEASE_MANIFEST.sha256 covers every release file except itself; the external ZIP .sha256 covers the archive. These are integrity checks, not signatures.

## Remaining target-host checks

No live Proxmox/PBS backup or restore, Linux executable, Home Assistant action, Pushover delivery, MQTT broker/TLS session or email relay/inbox delivery was tested. Real mail is delegated to vzdump: preflight/launch failures and terminated jobs cannot guarantee email. Preflight failures stop before MQTT too. Successful sendmail submission indicates local acceptance only.

Existing limits remain: deadlines kill/reap the direct subprocess only, so PVE workers may continue; MQTT publish timeout does not bound DNS/connection establishment; real backup exit status is preserved on MQTT failure. Error filtering recognizes explicit severity prefixes; unlabelled continuation text stays in the full log. Config errors precede log initialization. Disk exhaustion/kernel I/O and process-tree cancellation were not tested. Old retained success events can replay, and the automation has no durable duplicate suppression; dry-runs never request maintenance.
