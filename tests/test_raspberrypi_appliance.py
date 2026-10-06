import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

firstboot = load('rpi_firstboot', 'appliance/raspberrypi/firstboot.py')
updater = load('rpi_updater', 'appliance/raspberrypi/updater.py')
benchmark = load('benchmark', 'appliance/common/benchmark.py')

class LiteTests(unittest.TestCase):
    def test_firstboot_retries_after_expansion_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / 'state'
            config = Path(folder) / 'config'; config.mkdir()
            env = config / 'secrets.env'; env.write_text('ADMIN_PASSWORD=change-me-now\n')
            with self.assertRaises(RuntimeError):
                firstboot.initialize(config, state, Mock(side_effect=RuntimeError('grow failed')))
            self.assertFalse((state / 'raspberrypi-initialized').exists())
            self.assertNotIn('change-me-now', env.read_text())
            grow = Mock()
            firstboot.initialize(config, state, grow)
            identity = (state / 'machine-id').read_text()
            secret = env.read_text()
            firstboot.initialize(config, state, grow)
            grow.assert_called_once()
            self.assertNotIn('change-me-now', secret)
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)
            self.assertEqual(identity, (state / 'machine-id').read_text())
            self.assertEqual(secret, env.read_text())

    def test_rejects_old_release_before_activation(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, 'predates Lite'):
                updater.compatible(Path(folder))

    def test_failed_new_release_restores_old_link(self):
        with tempfile.TemporaryDirectory() as folder:
            releases = Path(folder).resolve()
            old = releases / 'initial-image'; old.mkdir()
            (old / '.source-commit').write_text('a'*40)
            app = releases / 'app'; app.symlink_to(old)
            def prepare(target, sha): target.mkdir()
            def activate(target):
                app.unlink(); app.symlink_to(target)
            # Layout check is intentionally strict: use a patched Path factory for
            # the literal production directory while all mutation stays in tmp.
            real_path = Path
            def paths(value): return releases if value == '/opt/pi-home-releases' else real_path(value)
            with patch.object(updater, 'APP', app), patch.object(updater, 'Path', side_effect=paths), patch.object(updater.os, 'chdir'), patch.object(updater.shared, 'wait_for_clock'), patch.object(updater.shared, 'status'), patch.object(updater, 'select_revision', return_value='b'*40), patch.object(updater.shared, 'prune_releases'), patch.object(updater.shared, 'required_stage_space', return_value=1), patch.object(updater, 'prepare', side_effect=prepare), patch.object(updater.shared, 'activate', side_effect=activate), patch.object(updater, 'restart') as restart, patch.object(updater, 'healthy', side_effect=[False, True]):
                with self.assertRaisesRegex(RuntimeError, 'previous working application restored'):
                    updater.update()
                self.assertEqual(app.resolve(), old)
                self.assertEqual(restart.call_count, 2)
                self.assertEqual(list(releases.glob('b'*40+'-*')), [])

    def test_benchmark_reports_resident_memory_and_bridge_children(self):
        with tempfile.TemporaryDirectory() as folder:
            proc = Path(folder)
            for pid, command in [(10, b'/opt/RoonBridge/Bridge/RoonBridge\0'), (11, b'/opt/RoonBridge/RAATServer/RAATServer\0'), (12, b'node\0/opt/pi-home/roon-controller/server.js\0')]:
                path = proc / str(pid); path.mkdir()
                (path / 'cmdline').write_bytes(command)
                (path / 'status').write_text('VmSize: 999999 kB\nVmRSS: 1234 kB\n')
                (path / 'smaps_rollup').write_text('Pss: 1000 kB\n')
            values = benchmark.processes(proc)
            self.assertEqual([v['category'] for v in sorted(values,key=lambda v:v['pid'])], ['bridge','bridge','controller'])
            self.assertTrue(all(v['rss_kib'] == 1234 and v['pss_kib'] == 1000 for v in values))
