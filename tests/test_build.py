"""Build contract tests use a fake bundler; never install or compile dependencies."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pbs_build', ROOT / 'build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class BuildTests(unittest.TestCase):
    """Protect private files and verify the declared bundle dependencies."""

    def test_existing_bundle_refused(self):
        """An existing deployment, including private settings, must never be overwritten."""
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'pbs-backup'
            dest.mkdir()
            private = dest / 'config.toml'
            private.write_text('keep me')
            with patch.object(sys, 'argv', ['build.py', '--output-dir', tmp]), \
                 patch.object(builder.subprocess, 'run') as run, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    builder.main()
                run.assert_not_called()
                self.assertEqual(private.read_text(), 'keep me')

    def test_missing_dependency_refused(self):
        """Missing build dependencies fail before starting a build or creating output."""
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'output'
            with patch.object(sys, 'argv', ['build.py', '--output-dir', str(output)]), \
                 patch.object(builder.importlib.util, 'find_spec', return_value=None), \
                 patch.object(builder.subprocess, 'run') as run, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    builder.main()
                run.assert_not_called()
                self.assertFalse(output.exists())

    def test_bundle_contents_and_cleanup(self):
        """Collect app/MQTT/Tomli, copy only public deployment files and clean scratch work."""
        with tempfile.TemporaryDirectory() as tmp:
            output, work = Path(tmp) / 'output', Path(tmp) / 'work'
            def fake_bundler(command, **kwargs):
                """Represent successful PyInstaller output without running a compiler."""
                self.assertEqual(command[:3], [sys.executable, '-m', 'PyInstaller'])
                for module in ('pbs_backup', 'paho.mqtt', 'tomli'):
                    self.assertIn(module, command)
                self.assertIn('--onedir', command)
                self.assertEqual(kwargs['cwd'], ROOT)
                self.assertTrue(kwargs['check'])
                self.assertTrue(Path(kwargs['env']['PYINSTALLER_CONFIG_DIR']).parent.is_dir())
                dest = output / 'pbs-backup'
                dest.mkdir(parents=True)
                (dest / '_internal').mkdir()
                (dest / 'pbs-backup').write_text('fake executable')
            with patch.object(sys, 'argv', ['build.py', '--output-dir', str(output), '--work-dir', str(work)]), \
                 patch.object(builder.importlib.util, 'find_spec', return_value=object()), \
                 patch.object(builder.subprocess, 'run', side_effect=fake_bundler), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(builder.main(), 0)
            dest = output / 'pbs-backup'
            self.assertEqual({p.name for p in dest.iterdir()},
                             {'pbs-backup', '_internal', 'config.example.toml', 'README.md', 'LEGAL.md', 'VERSION', 'homeassistant'})
            self.assertEqual((dest / 'config.example.toml').read_bytes(), (ROOT / 'config.example.toml').read_bytes())
            self.assertEqual(list(work.iterdir()), [])

    def test_failed_build_cleanup(self):
        """Report failed compilation and remove scratch space without deleting partial output."""
        with tempfile.TemporaryDirectory() as tmp:
            output, work = Path(tmp) / 'output', Path(tmp) / 'work'
            with patch.object(sys, 'argv', ['build.py', '--output-dir', str(output), '--work-dir', str(work)]), \
                 patch.object(builder.importlib.util, 'find_spec', return_value=object()), \
                 patch.object(builder.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'PyInstaller')), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(builder.main(), 1)
            self.assertEqual(list(work.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
