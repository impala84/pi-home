import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pi_bus_time_display.server import write_control_request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("alpine_firstboot", ROOT / "appliance/alpine/firstboot.py")
firstboot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(firstboot)


class AlpinePrototypeTests(unittest.TestCase):
    def test_unsupported_privileged_actions_fail_without_queuing(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"PI_HOME_APPLIANCE_PLATFORM": "alpine-prototype"}):
            state = Path(folder)
            for action in ("update", "reboot", "set_wifi", "set_display", "roon_start", "set_brightness"):
                with self.assertRaisesRegex(ValueError, "unavailable in the Alpine prototype"):
                    write_control_request(state, {"action": action})
            self.assertEqual(list(state.iterdir()), [])

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


if __name__ == "__main__":
    unittest.main()
