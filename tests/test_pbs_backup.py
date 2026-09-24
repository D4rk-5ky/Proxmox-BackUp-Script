"""Offline regression checks: no root privileges, Proxmox, or MQTT connection needed."""
from email import policy
from email.parser import BytesParser
import contextlib
import io
import json
import logging
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

SCRIPT = Path(__file__).resolve().parents[1] / 'pbs-backup'
APP = runpy.run_path(str(SCRIPT))
G = APP['main'].__globals__
BASE = ['--storage', 'pbs-storage', '--mqtt-host', 'broker.invalid', '--mqtt-topic', 'test/backup']


class BackupTests(unittest.TestCase):
    """Exercise selection, deadlines, dry-run, status publication, and input guards."""

    def setUp(self):
        """Allocate private logs and a quiet logger for each isolated test."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / 'test.toml'
        self.config.write_text('')
        self.logfile = str(Path(self.tmp.name) / 'test.log')
        self.errfile = str(Path(self.tmp.name) / 'test.err')
        self.logger = logging.getLogger('pbs-test')
        self.logger.addHandler(logging.NullHandler())

    def tearDown(self):
        """Close app handlers so repeated main calls cannot reuse another test's log."""
        for logger in (logging.getLogger('pbs_backup'), self.logger):
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)

    def args(self, *extra):
        """Parse realistic command lines using the application's existing parser."""
        with patch.object(sys, 'argv', ['pbs-backup', '--config', str(self.config), *BASE, *extra]):
            return APP['parse_args']()

    def run_child(self, code, timeout=None):
        """Run a harmless Python child through the real streaming/deadline code."""
        with contextlib.redirect_stdout(io.StringIO()):
            self.logger = APP['setup_logger'](self.logfile, self.errfile)
            return APP['run_command_stream'](
                [sys.executable, '-c', code], self.logger,
                self.logfile, self.errfile, timeout=timeout)

    def call_main(self, extra=(), root=True, executable='/mock/vzdump', mqtt=object(), rc=0, publish_error=None):
        """Mock external boundaries while retaining parsing and main orchestration."""
        with patch.object(sys, 'argv', ['pbs-backup', '--config', str(self.config), *BASE, '--log-dir', self.tmp.name, *extra]), \
             patch.dict(G, is_root=lambda: root, mqtt=mqtt), \
             patch.object(G['shutil'], 'which', return_value=executable), \
             patch.dict(G, run_command_stream=MagicMock(return_value=rc), publish_backup_status=MagicMock(side_effect=publish_error)), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = APP['main']()
            return result, G['run_command_stream'], G['publish_backup_status']

    def test_original_defaults(self):
        """Keep all guests, snapshot, zstd, unlimited bandwidth, and MQTT defaults."""
        args = self.args()
        self.assertTrue(args.all)
        self.assertEqual((args.mode, args.compress, args.bwlimit), ('snapshot', 'zstd', 0))
        self.assertEqual((args.mqtt_port, args.mqtt_qos, args.mqtt_timeout), (1883, 1, 15))
        self.assertFalse(args.mqtt_tls or args.mqtt_insecure or args.mqtt_retain)
        self.assertIsNone(args.timeout)
        self.assertFalse(args.dry_run_mqtt or args.dry_run_email)
        self.assertIn('--all', APP['build_vzdump_cmd'](args))

    def test_invalid_input_rejected(self):
        """Reject inputs that could broaden selection or silently disable safeguards."""
        cases = [('--vmid', '100'), ('--all', '--no-all', '--vmid', '100'),
                 ('--no-all',), ('--exclude',), ('--exclude', '-1'),
                 ('--no-all', '--vmid', 'abc'), ('--timeout', '0'), ('--timeout', '-1'),
                 ('--bwlimit', '-1'), ('--mqtt-timeout', '0'), ('--mqtt-port', '65536'),
                 ('--mqtt-port', '0'), ('--mqtt-topic', 'test/#'), ('--mqtt-topic', ''),
                 ('--mqtt-insecure',), ('--mqtt-cafile', 'ca.pem'), ('--mqtt-pass', 'secret'),
                 ('--log-prefix', '../escape'), ('--storage', '')]
        for extra in cases:
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    self.args(*extra)
                self.assertEqual(caught.exception.code, 2)

    def test_explicit_exclusions(self):
        """Subtract exclusions locally; never send conflicting VMIDs and --exclude."""
        args = self.args('--no-all', '--vmid', '0100', '101', '--exclude', '100')
        APP['resolve_selection'](args)
        cmd = APP['build_vzdump_cmd'](args)
        self.assertEqual(cmd[:4], ['vzdump', '101', '--all', '0'])
        self.assertNotIn('--exclude', cmd)

    def test_empty_selection_refused(self):
        """Removing the last explicitly selected guest must not fall back to all."""
        args = self.args('--no-all', '--vmid', '100', '--exclude', '100')
        with self.assertRaises(ValueError):
            APP['resolve_selection'](args)

    def test_all_exclusions_single_list(self):
        """Forward every excluded guest as one Proxmox VMID-list value."""
        args = self.args('--exclude', '100', '101')
        APP['resolve_selection'](args)
        cmd = APP['build_vzdump_cmd'](args)
        self.assertEqual(cmd.count('--exclude'), 1)
        self.assertEqual(cmd[cmd.index('--exclude') + 1], '100,101')

    def test_running_selection(self):
        """Use only local running QEMU/LXC guests and respect explicit filters."""
        guests = [{'node': 'pve1', 'type': 'qemu', 'vmid': 100, 'status': 'running'},
                  {'node': 'pve1', 'type': 'lxc', 'vmid': 101, 'status': 'running'},
                  {'node': 'pve1', 'type': 'qemu', 'vmid': 102, 'status': 'stopped'},
                  {'node': 'pve2', 'type': 'qemu', 'vmid': 103, 'status': 'running'}]
        for extra, expected in [(('--exclude', '101'), ['100']),
                                (('--no-all', '--vmid', '101', '102', '103'), ['101'])]:
            args = self.args('--only-running', *extra)
            with patch.object(G['shutil'], 'which', return_value='/mock/pvesh'), \
                 patch.object(G['os'], 'uname', return_value=MagicMock(nodename='pve1.example')), \
                 patch.object(G['subprocess'], 'run', return_value=MagicMock(stdout=json.dumps(guests))) as query:
                APP['resolve_selection'](args)
                self.assertEqual(query.call_args.args[0], ['pvesh', 'get', '/cluster/resources', '--type', 'vm', '--output-format', 'json'])
            self.assertEqual(args.vmid, expected)
            self.assertFalse(args.all)
            self.assertNotIn('--only-running', APP['build_vzdump_cmd'](args))

    def test_running_query_failures(self):
        """Missing tools, invalid inventory, and query failures cannot trigger backups."""
        with patch.object(G['shutil'], 'which', return_value=None):
            with self.assertRaises(ValueError):
                APP['resolve_selection'](self.args('--only-running'))
        for data in ['[]', '{}', '[123]', 'not json']:
            with patch.object(G['shutil'], 'which', return_value='/mock/pvesh'), \
                 patch.object(G['subprocess'], 'run', return_value=MagicMock(stdout=data)):
                with self.assertRaises(ValueError):
                    APP['resolve_selection'](self.args('--only-running'))
        for error in [subprocess.CalledProcessError(1, 'pvesh'), subprocess.TimeoutExpired('pvesh', 30)]:
            with patch.object(G['shutil'], 'which', return_value='/mock/pvesh'), \
                 patch.object(G['subprocess'], 'run', side_effect=error):
                with self.assertRaises(subprocess.SubprocessError):
                    APP['resolve_selection'](self.args('--only-running'))

    def test_literal_arguments(self):
        """Keep notes as a single argv value, without shell interpolation."""
        note = '{{guestname}}; $(touch /not-executed)'
        cmd = APP['build_vzdump_cmd'](self.args('--notes-template', note, '--quiet', '--mailto', 'a@example.invalid', '--mailnotification', 'failure'))
        self.assertEqual(cmd[cmd.index('--notes-template') + 1], note)
        self.assertEqual(cmd[cmd.index('--quiet') + 1], '1')
        self.assertIn('a@example.invalid', cmd)

    def test_streams_and_exit_status(self):
        """Keep both streams in the full log and only errors/failure summary in .err."""
        rc = self.run_child("import sys;print('INFO: stdout');print('INFO: stderr',file=sys.stderr);print('ERROR: broken disk');sys.stdout.write('partial');sys.exit(7)")
        self.assertEqual(rc, 7)
        text = Path(self.logfile).read_text()
        for token in ('stdout', 'stderr', 'partial', 'rc=7', 'broken disk'):
            self.assertIn(token, text)
        error = Path(self.errfile).read_text()
        self.assertIn('broken disk', error)
        self.assertIn('rc=7', error)
        for token in ('INFO:', 'partial', 'Finished', 'Running:'):
            self.assertNotIn(token, error)

    def test_silent_timeout(self):
        """Enforce the deadline even when the child never emits a newline."""
        start = time.monotonic()
        self.assertEqual(self.run_child('import time;time.sleep(10)', timeout=1), 255)
        self.assertLess(time.monotonic() - start, 5)

    def test_partial_line_timeout(self):
        """A flushed fragment without newline cannot block deadline enforcement."""
        start = time.monotonic()
        self.assertEqual(self.run_child("import sys,time;sys.stdout.write('partial');sys.stdout.flush();time.sleep(10)", timeout=1), 255)
        self.assertLess(time.monotonic() - start, 5)
        self.assertIn('partial', Path(self.logfile).read_text())

    def test_closed_pipe_timeout(self):
        """Apply the same deadline to a child that closes its output then sleeps."""
        start = time.monotonic()
        self.assertEqual(self.run_child('import os,time;os.close(1);os.close(2);time.sleep(10)', timeout=1), 255)
        self.assertLess(time.monotonic() - start, 5)

    def test_invalid_output_bytes(self):
        """Undecodable output must not discard the child result or abort logging."""
        self.assertEqual(self.run_child("import os;os.write(1,b'bad\\xff')"), 0)
        self.assertIn('bad', Path(self.logfile).read_text())

    def test_launch_failure_returns_error(self):
        """A missing executable produces rc=255 so main can publish failure."""
        with patch.object(G['subprocess'], 'Popen', side_effect=FileNotFoundError('missing')):
            self.assertEqual(self.run_child('pass'), 255)
        self.assertIn('missing', Path(self.errfile).read_text())

    def test_dry_run_never_launches_child(self):
        """The streaming helper's dry-run branch must not spawn any process."""
        with patch.object(G['subprocess'], 'Popen') as spawn:
            self.assertEqual(APP['run_command_stream'](['vzdump'], self.logger, self.logfile, self.errfile, dry_run=True), 0)
            spawn.assert_not_called()

    def test_main_dry_run_never_publishes(self):
        """A default preview sends no MQTT without the new explicit opt-in."""
        rc, run, publish = self.call_main(('--dry-run',))
        self.assertEqual(rc, 0)
        self.assertTrue(run.call_args.kwargs['dry_run'])
        publish.assert_not_called()

    def test_preflight_guards(self):
        """Root, vzdump, and Paho checks remain mandatory, even for previews."""
        for kwargs in [{'root': False}, {'executable': None}, {'mqtt': None}]:
            for extra in [(), ('--dry-run',)]:
                rc, run, publish = self.call_main(extra, **kwargs)
                self.assertEqual(rc, 2)
                run.assert_not_called()
                publish.assert_not_called()

    def test_no_guests_main(self):
        """Main converts an empty resolved selection into a preflight failure."""
        rc, run, publish = self.call_main(('--no-all', '--vmid', '100', '--exclude', '100'))
        self.assertEqual(rc, 2)
        run.assert_not_called()
        publish.assert_not_called()

    def test_backup_results_and_mqtt_failure(self):
        """Publish actual run results; preserve backup exit status if MQTT fails."""
        for code in [0, 7, 255]:
            rc, run, publish = self.call_main(rc=code, publish_error=RuntimeError('offline'))
            self.assertEqual(rc, code)
            self.assertEqual(publish.call_args.kwargs['rc'], code)

    def test_payload_mapping(self):
        """Status derives from rc and err_file reflects file content, not success."""
        for code, expected in [(0, 'success'), (9, 'error')]:
            with patch.dict(G, mqtt_publish=MagicMock()):
                APP['publish_backup_status'](rc=code, duration_s=3, node='pve1', storage='pbs',
                    log_file=self.logfile, err_file=self.errfile, mqtt_host='invalid', mqtt_port=1883,
                    mqtt_topic='test', mqtt_user=None, mqtt_pass=None, mqtt_tls=False, mqtt_cafile=None,
                    mqtt_insecure=False, mqtt_client_id='test', mqtt_retain=False, mqtt_qos=1,
                    mqtt_timeout=15, logger=self.logger)
                payload = G['mqtt_publish'].call_args.kwargs['payload']
                self.assertEqual(payload['status'], expected)
                self.assertIsNone(payload['err_file'])

    def test_mqtt_publish_cleanup(self):
        """Both Paho API paths configure TLS/auth and clean up after publish or timeout."""
        for legacy in (False, True):
            for completed in (False, True):
                mqtt = MagicMock()
                client = MagicMock()
                mqtt.Client.side_effect = [TypeError('legacy'), client] if legacy else None
                mqtt.Client.return_value = client
                client.publish.return_value.is_published.return_value = completed
                with patch.dict(G, mqtt=mqtt):
                    kwargs = dict(host='invalid', port=8883, topic='test', payload={'rc': 0},
                        username='u', password='p', tls=True, cafile='ca.pem', insecure=False,
                        client_id='test', retain=True, qos=1, logger=self.logger)
                    if completed:
                        APP['mqtt_publish'](**kwargs)
                    else:
                        with self.assertRaises(TimeoutError):
                            APP['mqtt_publish'](**kwargs)
                client.username_pw_set.assert_called_once_with('u', password='p')
                client.tls_set.assert_called_once_with(ca_certs='ca.pem')
                client.tls_insecure_set.assert_not_called()
                client.disconnect.assert_called_once()
                client.loop_stop.assert_called_once()
                client.on_disconnect(client, None, 'flags', 'reason', None)
                client.on_disconnect(client, None, 0)


    def config_args(self, text, *overrides):
        """Parse TOML without required CLI settings to exercise config-first usage."""
        self.config.write_text(text)
        with patch.object(sys, 'argv', ['pbs-backup', '--config', str(self.config), *overrides]):
            return APP['parse_args']()

    def valid_config(self):
        """Provide minimal configured destinations, leaving other settings at defaults."""
        return '[backup]\nstorage="pbs-test"\n[mqtt]\nhost="broker.invalid"\ntopic="test/backup"\n'

    def test_config_only_and_precedence(self):
        """Use TOML alone and let an explicit CLI value override it without losing others."""
        args = self.config_args(self.valid_config())
        self.assertEqual((args.storage, args.mqtt_host, args.mqtt_topic), ('pbs-test', 'broker.invalid', 'test/backup'))
        self.assertEqual(args.log_dir, str(G['SCRIPT_DIR'] / 'logs'))
        args = self.config_args(self.valid_config(), '--storage', 'override', '--dry-run')
        self.assertEqual(args.storage, 'override')
        self.assertEqual(args.mqtt_host, 'broker.invalid')
        self.assertTrue(args.dry_run)

    def test_config_category_casing(self):
        """Resolve every category identically in uppercase, lowercase, or mixed case."""
        template = (SCRIPT.parent / 'config.example.toml').read_text()
        template = template.replace('storage = ""', 'storage = "pbs"').replace('host = ""', 'host = "broker.invalid"').replace('topic = ""', 'topic = "test"')
        expected = vars(self.config_args(template))
        for transform in (str.lower, str.title):
            text = template
            for section in G['CONFIG_SECTIONS']:
                text = text.replace('[' + section.upper() + ']', '[' + transform(section) + ']')
            self.assertEqual(vars(self.config_args(text)), expected)

    def test_config_duplicate_categories_rejected(self):
        """Never merge different spellings of the same category, even disjoint keys."""
        for extra in ('[MQTT]\nport=1883\n', '[BaCkUp]\ndry_run=true\n'):
            output = io.StringIO()
            with contextlib.redirect_stderr(output), self.assertRaises(SystemExit) as caught:
                self.config_args(self.valid_config() + extra)
            self.assertEqual(caught.exception.code, 2)
            self.assertIn('Duplicate TOML category', output.getvalue())

    def test_config_key_casing_stays_strict(self):
        """Uppercase categories do not silently accept misspelled option keys."""
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            self.config_args(self.valid_config().replace('storage=', 'Storage='))
        self.assertEqual(caught.exception.code, 2)

    def test_default_config_missing_never_loads_templates(self):
        """Missing private config fails even when configured templates are present."""
        appdir = Path(self.tmp.name)
        for name in ('config.example.toml', 'pbs-backup.toml'):
            (appdir / name).write_text(self.valid_config())
        with patch.dict(G, SCRIPT_DIR=appdir), patch.object(sys, 'argv', ['pbs-backup']), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            APP['parse_args']()
        self.assertEqual(caught.exception.code, 2)

    def test_config_all_options(self):
        """Load all shipped keys and correctly convert unset strings, arrays and timeout."""
        text = (SCRIPT.parent / 'config.example.toml').read_text()
        text = text.replace('storage = ""', 'storage = "pbs"').replace('host = ""', 'host = "broker.invalid"').replace('topic = ""', 'topic = "test"')
        args = self.config_args(text)
        self.assertTrue(args.dry_run)
        self.assertIsNone(args.timeout)
        self.assertIsNone(args.mqtt_pass)
        self.assertIsNone(args.mqtt_cafile)
        data = G['tomllib'].loads(text)
        self.assertEqual(sum(len(section) for section in data.values()), sum(map(len, G['CONFIG_SECTIONS'].values())))
        text = text.replace('all = true\n', 'all = false\n').replace('vmid = []', 'vmid = [100, "0101"]').replace('exclude = []', 'exclude = [100]')
        args = self.config_args(text)
        APP['resolve_selection'](args)
        self.assertEqual(args.vmid, ['101'])

    def test_config_invalid_types_keys_and_choices(self):
        """Reject TOML typos, invalid choices and bool/integer confusion before running."""
        cases = ['[unknown]\na=1', '[backup]\nstorage="x"\nwat=true',
                 '[backup]\nbwlimit=true', '[backup]\nmode="bad"',
                 '[backup]\ndry_run="false"', '[backup]\nstorage=1',
                 '[selection]\nvmid=[true]', '[selection]\nvmid="100"',
                 '[mqtt]\nqos=9', '[mqtt]\nport=1.5', '[backup]\ntimeout=-1',
                 '[mqtt]\ntimeout=0', 'backup="oops"', '[logging]\nlog_dir=""']
        for text in cases:
            with self.subTest(text=text), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    self.config_args(text)
                self.assertEqual(caught.exception.code, 2)

    def test_config_syntax_and_secret_not_echoed(self):
        """Syntax errors and invalid password types must not dump secret-bearing values."""
        for text in ['[mqtt]\npass="TOPSECRET"\npass="other"', '[mqtt]\npass=["TOPSECRET"]', 'broken = [']:
            output = io.StringIO()
            with contextlib.redirect_stderr(output), self.assertRaises(SystemExit):
                self.config_args(text)
            self.assertNotIn('TOPSECRET', output.getvalue())

    def test_missing_config_and_missing_parser(self):
        """Fail closed for unreadable config or unavailable TOML support; no fallback run."""
        self.config.unlink()
        with patch.object(sys, 'argv', ['pbs-backup', '--config', str(self.config)]), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                APP['parse_args']()
        with patch.dict(G, tomllib=None), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.config_args(self.valid_config())

    def test_help_and_version_without_config(self):
        """Inspection commands work even if TOML/Paho/config files are unavailable."""
        for flag in ['--help', '--version']:
            with patch.dict(G, tomllib=None, mqtt=None), patch.object(sys, 'argv', ['pbs-backup', '--config', '/missing', flag]), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    APP['parse_args']()
                self.assertEqual(caught.exception.code, 0)

    def test_config_relative_paths(self):
        """Anchor TOML CA paths to config and log paths to script, independent of cwd."""
        text = self.valid_config() + 'tls=true\ncafile="certs/ca.pem"\n[logging]\nlog_dir="mylogs"\n'
        args = self.config_args(text)
        self.assertEqual(args.mqtt_cafile, str(self.config.parent.resolve() / 'certs/ca.pem'))
        self.assertEqual(args.log_dir, str(G['SCRIPT_DIR'] / 'mylogs'))

    def test_no_flags_creates_script_local_logs(self):
        """Run a configured preview from another cwd without backup/MQTT side effects."""
        appdir = Path(self.tmp.name) / 'app'
        appdir.mkdir()
        (appdir / 'config.toml').write_text(self.valid_config().replace('[mqtt]', 'dry_run=true\n[mqtt]'))
        old_cwd = Path.cwd()
        try:
            G['os'].chdir(self.tmp.name)
            with patch.dict(G, SCRIPT_DIR=appdir, is_root=lambda: True, mqtt=object(), publish_backup_status=MagicMock()),                  patch.object(G['shutil'], 'which', return_value='/mock/vzdump'),                  patch.object(G['subprocess'], 'Popen') as spawn,                  patch.object(sys, 'argv', ['pbs-backup']), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(APP['main'](), 0)
                spawn.assert_not_called()
                G['publish_backup_status'].assert_not_called()
            self.assertEqual(len(list((appdir / 'logs').glob('*.log'))), 1)
            self.assertFalse((Path(self.tmp.name) / 'logs').exists())
            self.assertFalse(any(f.stat().st_size for f in (appdir / 'logs').glob('*.err')))
        finally:
            G['os'].chdir(old_cwd)

    def test_success_keeps_error_log_empty(self):
        """INFO/WARN on stderr and incidental error words are not error messages."""
        code = "import sys;print('INFO: no errors occurred');print('INFO: progress',file=sys.stderr);print('WARN: retry recovered',file=sys.stderr)"
        self.assertEqual(self.run_child(code), 0)
        self.assertEqual(Path(self.errfile).read_text(), '')
        self.assertIn('retry recovered', Path(self.logfile).read_text())

    def test_error_severity_prefixes(self):
        """Recognize explicit error levels, including guest/timestamp and TASK prefixes."""
        for line in ['ERROR: broken', 'TASK ERROR: broken', 'FATAL: broken', 'CRITICAL: broken',
                     '100: ERROR: broken', '100: 2026-09-24 12:34:56 ERROR: broken']:
            self.assertTrue(APP['is_error_line'](line), line)
        for line in ['INFO: ERROR: quoted text', 'WARN: temporary error', '0 errors', 'progress', 'not an ERROR: message']:
            self.assertFalse(APP['is_error_line'](line), line)

    def test_split_error_line_and_final_fragment(self):
        """Error filtering survives chunk splits and an error without a final newline."""
        code = "import os,time;os.write(1,b'ERR');time.sleep(.1);os.write(1,b'OR: split failure\\n');os.write(2,b'TASK ERROR: final fragment')"
        self.assertEqual(self.run_child(code), 0)
        error = Path(self.errfile).read_text()
        self.assertIn('ERROR: split failure', error)
        self.assertIn('TASK ERROR: final fragment', error)
        self.assertNotIn('Finished', error)

    def test_wrapper_errors_and_logger_reinitialization(self):
        """Separate wrapper errors from INFO/WARN and switch paths between runs."""
        with contextlib.redirect_stdout(io.StringIO()):
            logger = APP['setup_logger'](self.logfile, self.errfile)
            logger.info('ordinary progress')
            logger.warning('warning only')
            logger.error('MQTT publish failed: offline')
            error = Path(self.errfile).read_text()
            self.assertIn('MQTT publish failed', error)
            self.assertNotIn('ordinary progress', error)
            self.assertNotIn('warning only', error)
            other = str(Path(self.tmp.name) / 'other')
            logger = APP['setup_logger'](other + '.log', other + '.err')
            logger.error('second run')
            self.assertNotIn('second run', Path(self.errfile).read_text())
            self.assertIn('second run', Path(other + '.err').read_text())

    def test_preflight_and_mqtt_errors_written(self):
        """Capture runtime preflight/MQTT failures in .err without progress noise."""
        self.call_main(root=False)
        self.call_main(publish_error=RuntimeError('broker offline'))
        errors = '\n'.join(f.read_text() for f in Path(self.tmp.name).glob('*.err'))
        self.assertIn('Must run as root', errors)
        self.assertIn('MQTT publish failed', errors)
        self.assertNotIn('INFO', errors)



    def run_notifications(self, mqtt_enabled, email_enabled, *, dry_run=True, mqtt_error=None, email_error=None):
        """Run the real dry-run path with notification boundaries mocked and no child allowed."""
        config = self.valid_config().replace('[mqtt]',
            f'dry_run={str(dry_run).lower()}\ndry_run_mqtt={str(mqtt_enabled).lower()}\n'
            f'dry_run_email={str(email_enabled).lower()}\n[mqtt]')
        config += f'[mail]\nmailto="admin@example.invalid"\n[logging]\nlog_dir="{self.tmp.name}"\n'
        self.config.write_text(config)
        mail = MagicMock(side_effect=email_error)
        publish = MagicMock(side_effect=mqtt_error)
        with patch.object(sys, 'argv', ['pbs-backup', '--config', str(self.config)]), \
             patch.dict(G, is_root=lambda: True, mqtt=object(), send_dry_run_email=mail, publish_backup_status=publish), \
             patch.object(G['shutil'], 'which', return_value='/mock/vzdump'), \
             patch.object(G['subprocess'], 'Popen', side_effect=AssertionError('No backup allowed in notification tests')), \
             contextlib.redirect_stdout(io.StringIO()):
            if dry_run:
                rc = APP['main']()
            else:
                with patch.dict(G, run_command_stream=MagicMock(return_value=0)):
                    rc = APP['main']()
        return rc, mail, publish

    def test_dry_run_notification_matrix(self):
        """All four opt-in combinations leave backup execution disabled and send only requested channels."""
        for mqtt_enabled in (False, True):
            for email_enabled in (False, True):
                with self.subTest(mqtt=mqtt_enabled, email=email_enabled):
                    rc, mail, publish = self.run_notifications(mqtt_enabled, email_enabled)
                    self.assertEqual(rc, 0)
                    self.assertEqual(mail.call_count, int(email_enabled))
                    self.assertEqual(publish.call_count, int(mqtt_enabled))
                    if mqtt_enabled:
                        self.assertTrue(publish.call_args.kwargs['dry_run'])

    def test_notification_failures_attempt_other_channel(self):
        """Requested notification failures return 3, log errors, and do not skip the other channel."""
        for mqtt_error, email_error in [(RuntimeError('MQTT offline'), None),
                                        (None, RuntimeError('email offline')),
                                        (RuntimeError('MQTT offline'), RuntimeError('email offline'))]:
            rc, mail, publish = self.run_notifications(True, True, mqtt_error=mqtt_error, email_error=email_error)
            self.assertEqual(rc, 3)
            mail.assert_called_once()
            publish.assert_called_once()
        errors = '\n'.join(f.read_text() for f in Path(self.tmp.name).glob('*.err'))
        self.assertIn('Dry-run email failed', errors)
        self.assertIn('MQTT publish failed', errors)

    def test_real_backup_ignores_preview_options(self):
        """Real runs keep normal MQTT and vzdump email behavior with no extra test email."""
        rc, mail, publish = self.run_notifications(True, True, dry_run=False)
        self.assertEqual(rc, 0)
        mail.assert_not_called()
        publish.assert_called_once()
        self.assertFalse(publish.call_args.kwargs['dry_run'])

    def test_preview_mqtt_payload_and_routing(self):
        """Preview payload cannot look like backup success or replace retained real status."""
        with patch.dict(G, mqtt_publish=MagicMock()):
            APP['publish_backup_status'](rc=0, duration_s=0, node='pve1', storage='pbs',
                log_file=self.logfile, err_file=self.errfile, mqtt_host='invalid', mqtt_port=8883,
                mqtt_topic='backup/status', mqtt_user='test', mqtt_pass='secret', mqtt_tls=True,
                mqtt_cafile='ca.pem', mqtt_insecure=False, mqtt_client_id='test', mqtt_retain=True,
                mqtt_qos=2, mqtt_timeout=30, logger=self.logger, dry_run=True)
            kwargs = G['mqtt_publish'].call_args.kwargs
            self.assertEqual(kwargs['topic'], 'backup/status/dry-run')
            self.assertFalse(kwargs['retain'])
            self.assertEqual(kwargs['qos'], 2)
            payload = kwargs['payload']
            self.assertEqual(payload['status'], 'dry-run')
            self.assertIsNone(payload['rc'])
            self.assertTrue(payload['dry_run'])
            self.assertFalse(payload['backup_executed'])
            self.assertEqual(payload['preview_rc'], 0)
            self.assertNotIn('secret', json.dumps(payload))

    def test_dry_run_email_recipient_validation(self):
        """Reject missing, malformed and header-injected test recipients before notifications."""
        for value in [None, '', 'a@', 'a@@b', 'Name <a@b>', 'a@b,,c@d', '-Xfile',
                      'a@b\nBcc: hidden@example.invalid', 'a@b\r\nX: test', 'a@b\x00']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                APP['dry_run_recipients'](value)
        self.assertEqual(APP['dry_run_recipients']('a@example.invalid, root'), ['a@example.invalid', 'root'])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.args('--dry-run', '--dry-run-email')
        # A saved preview option must not change validation of real-run PVE recipients.
        self.args('--dry-run-email', '--mailto', 'pve-user@pam')

    def test_email_message_and_submission(self):
        """Build an explicit preview email and send it via bounded stdin, not a backup subprocess."""
        with patch.object(G['shutil'], 'which', return_value='/mock/sendmail'), \
             patch.object(G['subprocess'], 'run', return_value=MagicMock(returncode=0)) as submit:
            APP['send_dry_run_email'](mailto='a@example.invalid, root', node='pve1', storage='pbs',
                cmd=['vzdump', '--all', '--storage', 'pbs'], log_file=self.logfile,
                err_file=self.errfile, logger=self.logger)
        self.assertEqual(submit.call_args.args[0], ['/mock/sendmail', '-i', '-t'])
        self.assertEqual(submit.call_args.kwargs['timeout'], 30)
        self.assertNotIn('shell', submit.call_args.kwargs)
        msg = BytesParser(policy=policy.default).parsebytes(submit.call_args.kwargs['input'])
        self.assertIn('[DRY-RUN]', str(msg['Subject']))
        self.assertIn('NO BACKUP EXECUTED', str(msg['Subject']))
        self.assertIn('a@example.invalid', str(msg['To']))
        self.assertIsNone(msg['Bcc'])
        self.assertIn('not a backup result', msg.get_content())
        self.assertIn('Planned command (NOT executed)', msg.get_content())

    def test_email_transport_failures(self):
        """Surface missing sendmail, submission failure, and timeout without real delivery."""
        kwargs = dict(mailto='root', node='pve1', storage='pbs', cmd=['vzdump'],
                      log_file=self.logfile, err_file=self.errfile, logger=self.logger)
        with patch.object(G['shutil'], 'which', return_value=None), patch.object(G['os'], 'access', return_value=False):
            with self.assertRaises(RuntimeError):
                APP['send_dry_run_email'](**kwargs)
        with patch.object(G['shutil'], 'which', return_value='/mock/sendmail'), \
             patch.object(G['subprocess'], 'run', return_value=MagicMock(returncode=75, stderr=b'queue unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'queue unavailable'):
                APP['send_dry_run_email'](**kwargs)
        with patch.object(G['shutil'], 'which', return_value='/mock/sendmail'), \
             patch.object(G['subprocess'], 'run', side_effect=subprocess.TimeoutExpired('sendmail', 30)):
            with self.assertRaises(subprocess.TimeoutExpired):
                APP['send_dry_run_email'](**kwargs)

    def test_notification_config_types_and_cli(self):
        """Preview options are strict TOML booleans, default off, and explicitly overridable."""
        for key in ('dry_run_mqtt', 'dry_run_email'):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.config_args(self.valid_config().replace('[mqtt]', f'{key}="true"\n[mqtt]'))
        self.config.write_text('')
        args = self.args('--dry-run', '--dry-run-mqtt', '--dry-run-email', '--mailto', 'root')
        self.assertTrue(args.dry_run_mqtt and args.dry_run_email)


if __name__ == '__main__':
    unittest.main()
