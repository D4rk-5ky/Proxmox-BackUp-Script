#!/usr/bin/env python3
"""Build a native, self-contained onedir bundle without packaging private settings."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main() -> int:
    """Validate dependencies, build in scratch space and copy only public deployment files."""
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=root / "dist",
                        help="Parent of the new pbs-backup bundle; relative paths use the working directory.")
    parser.add_argument("--work-dir", type=Path, default=root / "build",
                        help="Parent for temporary PyInstaller work, spec and cache files; cleaned on exit.")
    args = parser.parse_args()
    if sys.platform not in ("linux", "darwin"):
        parser.error("Build on Linux for Proxmox; macOS is supported only for local packaging smoke checks.")
    output = args.output_dir.expanduser().resolve()
    destination = output / "pbs-backup"
    # PyInstaller can replace an output directory: never let it erase saved settings.
    if destination.exists() or destination.is_symlink():
        parser.error(f"Refusing to replace {destination}; choose a new --output-dir or move the old bundle first.")
    for module in ("PyInstaller", "paho.mqtt.client", "tomli"):
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ModuleNotFoundError):
            found = False
        if not found:
            parser.error(f"Missing build dependency {module}. Install requirements-build.txt in a virtual environment.")
    output.mkdir(parents=True, exist_ok=True)
    work = args.work_dir.expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    if sys.platform != "linux":
        print("NOTE: This produces a macOS test bundle, not a Linux/Proxmox executable.")
    with tempfile.TemporaryDirectory(prefix="pyinstaller-", dir=work) as temporary:
        scratch = Path(temporary)
        env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(scratch / "cache"), PYTHONDONTWRITEBYTECODE="1")
        command = [sys.executable, "-m", "PyInstaller", "--onedir", "--console", "--clean",
                   "--name", "pbs-backup", "--distpath", str(output),
                   "--workpath", str(scratch / "work"), "--specpath", str(scratch / "spec"),
                   "--paths", str(root), "--collect-submodules", "pbs_backup",
                   "--collect-submodules", "paho.mqtt", "--hidden-import", "tomli",
                   str(root / "pbs-backup")]
        try:
            subprocess.run(command, cwd=root, env=env, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"Build failed: {exc}. A partial output may remain at {destination}.", file=sys.stderr)
            return 1
    # These remain external so users can configure the bundle without rebuilding it.
    # Never copy config.toml, legacy private config candidates, logs, or credentials.
    for filename in ("config.example.toml", "README.md", "LEGAL.md", "VERSION"):
        shutil.copy2(root / filename, destination / filename)
    shutil.copytree(root / "homeassistant", destination / "homeassistant")
    print(f"Built {destination}. Deploy the entire folder, including _internal/.")
    print("Copy config.example.toml to config.toml beside the executable, then configure it.")
    print("The target still needs Proxmox vzdump/pvesh and local sendmail when used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
