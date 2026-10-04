import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from pi_bus_time_display.server import write_control_request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("alpine_firstboot", ROOT / "appliance/alpine/firstboot.py")
firstboot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(firstboot)
prepare_spec = importlib.util.spec_from_file_location("alpine_prepare", ROOT / "appliance/alpine/prepare_rootfs.py")
prepare_rootfs = importlib.util.module_from_spec(prepare_spec)
prepare_spec.loader.exec_module(prepare_rootfs)


class AlpinePrototypeTests(unittest.TestCase):
    def test_export_sanitizer_removes_container_identity_and_resets_network_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "etc").mkdir(); (root / "run").mkdir()
            (root / "etc/alpine-release").write_text("3.24.2")
            (root / "opt/pi-home/appliance/alpine").mkdir(parents=True)
            (root / ".dockerenv").touch(); (root / "run/.containerenv").touch()
            (root / "etc/hostname").write_text("docker-container-id")
            (root / "etc/resolv.conf").write_text("nameserver 127.0.0.11")
            prepare_rootfs.prepare(root)
            self.assertFalse((root / ".dockerenv").exists())
            self.assertFalse((root / "run/.containerenv").exists())
            self.assertEqual((root / "etc/hostname").read_text(), "pi-home-alpine\n")
            self.assertNotIn("127.0.0.11", (root / "etc/resolv.conf").read_text())
            prepare_rootfs.prepare(root)

    def test_export_sanitizer_rejects_live_root_and_non_image_tree(self):
        with self.assertRaises(ValueError): prepare_rootfs.prepare("/")
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): prepare_rootfs.prepare(folder)

    def test_unsupported_privileged_actions_fail_without_queuing(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"PI_HOME_APPLIANCE_PLATFORM": "alpine-prototype"}):
            state = Path(folder)
            for action in ("set_wifi", "set_display", "roon_start"):
                with self.assertRaisesRegex(ValueError, "unavailable in Alpine Beta"):
                    write_control_request(state, {"action": action})
            self.assertEqual(list(state.iterdir()), [])

    def test_alpine_backlight_actions_use_the_bounded_root_helper(self):
        client = Mock(); client.__enter__ = Mock(return_value=client); client.__exit__ = Mock(return_value=False)
        client.makefile.return_value.readline.return_value = b'{"ok":true}\n'
        with patch.dict(os.environ, {"PI_HOME_APPLIANCE_PLATFORM": "alpine-prototype"}), patch("pi_bus_time_display.server.socket.socket", return_value=client):
            self.assertTrue(write_control_request(Path("/unused"), {"action": "display_on", "brightness": 63}))
        self.assertEqual(client.sendall.call_args.args[0], b'{"action": "display_on", "brightness": 63}\n')
        with patch.dict(os.environ, {"PI_HOME_APPLIANCE_PLATFORM": "alpine-prototype"}):
            with self.assertRaisesRegex(ValueError, "between 10 and 100"):
                write_control_request(Path("/unused"), {"action": "set_brightness", "brightness": 0})

    def test_credentials_are_unique_private_and_idempotent(self):
        passwords = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as folder:
                config = Path(folder) / "config"
                state = Path(folder) / "state"
                config.mkdir(); state.mkdir()
                env = config / "secrets.env"
                env.write_text("ADMIN_PASSWORD=change-me-now\nADMIN_USERNAME=admin\n")
                firstboot.initialize(config, state)
                result = env.read_text()
                self.assertNotIn("change-me-now", result)
                self.assertIn("ADMIN_USERNAME=admin", result)
                self.assertEqual(env.stat().st_mode & 0o777, 0o600)
                firstboot.initialize(config, state)
                self.assertEqual(env.read_text(), result)
                passwords.append(result)
        self.assertNotEqual(*passwords)

    def test_existing_password_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config"; config.mkdir()
            state = Path(folder) / "state"; state.mkdir()
            env = config / "secrets.env"
            env.write_text("ADMIN_PASSWORD=already-configured\n")
            firstboot.initialize(config, state)
            self.assertEqual(env.read_text(), "ADMIN_PASSWORD=already-configured\n")

    def test_image_factory_never_targets_physical_disks(self):
        script = (ROOT / "appliance/alpine/build-image.sh").read_text()
        self.assertNotIn("/dev/sd", script)
        self.assertNotIn("/dev/mmc", script)
        self.assertNotIn("losetup", script)
        self.assertIn("--same-owner", script)
        self.assertIn("-d \"$build_dir/rootfs\"", script)
        self.assertIn("sha256sum", script)
        self.assertIn("mktemp -d", script)
        self.assertIn("pi-home-alpine-beta.img", script)
        self.assertNotIn("pi-home-alpine-prototype.img", script)


if __name__ == "__main__":
    unittest.main()
