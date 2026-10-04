import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("alpine_setup", ROOT / "appliance/alpine/setup_service.py")
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


class AlpineSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        config = self.root / "etc/pi-bus-time-display"; config.mkdir(parents=True)
        (config / "config.toml").write_text((ROOT / "config.example.toml").read_text())
        (config / "secrets.env").write_text("ADMIN_PASSWORD=old\nADMIN_USERNAME=admin\n")
        boot = self.root / "boot"; (boot / "overlays").mkdir(parents=True)
        (boot / "config.txt").write_text("arm_64bit=1\ndisplay_auto_detect=1\nkernel=vmlinuz-rpi\n")
        for overlay in module.PROFILES.values():
            if overlay: (boot / "overlays" / (overlay + ".dtbo")).touch()
        self.run = Mock(return_value="connected")
        self.setup = module.Setup(self.root, self.run, lambda: {"zones": [{"name": "Lounge"}]})

    def test_full_setup_persists_password_and_does_not_play_audio(self):
        self.setup.handle({"action": "name", "hostname": "Pi-Home-Lounge"})
        self.setup.handle({"action": "network"})
        self.setup.handle({"action": "roon", "zone": "Lounge"})
        self.setup.handle({"action": "display", "profile": "touch2-10", "rotation": "90", "timezone": "Europe/London", "theme": "roon"})
        self.setup.handle({"action": "finish", "password": "my-private-password"})
        self.assertTrue(self.setup.saved()["complete"])
        self.assertEqual((self.root / "etc/hostname").read_text(), "pi-home-lounge\n")
        config = (self.root / "etc/pi-bus-time-display/config.toml").read_text()
        self.assertIn('roon_zone_name = "Lounge"', config); self.assertIn('timezone = "Europe/London"', config)
        boot = (self.root / "boot/config.txt").read_text()
        self.assertIn("ili79600-10-1inch,swapxy,invx", boot); self.assertIn("kernel=vmlinuz-rpi", boot)
        self.assertNotIn("password", self.setup.progress.read_text())
        env = self.root / "etc/pi-bus-time-display/secrets.env"
        self.assertIn("ADMIN_PASSWORD=my-private-password", env.read_text()); self.assertEqual(env.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.run.call_args.args[0], ["rc-service", "pi-home-api", "restart"])

    def test_invalid_names_never_execute_commands(self):
        for name in ("-bad", "bad-", "x;reboot", "a b", "../root", "x\n", "x" * 64):
            with self.assertRaises(ValueError): self.setup.handle({"action": "name", "hostname": name})
        self.run.assert_not_called()

    def test_incomplete_and_invalid_finishes_are_rejected(self):
        with self.assertRaises(ValueError): self.setup.handle({"action": "finish", "password": "valid-password"})
        self.assertFalse(self.setup.progress.exists())

    def test_failed_wifi_does_not_save_network_or_password(self):
        self.run.side_effect = ValueError("Connection failed")
        with self.assertRaises(ValueError): self.setup.handle({"action": "wifi", "ssid": "Home", "password": "secret"})
        self.assertFalse(self.setup.progress.exists())

    def test_wifi_uses_argument_list_not_shell_and_keeps_secrets_out_of_progress(self):
        self.setup.handle({"action": "wifi", "ssid": "Home;not-a-command", "password": "private-secret"})
        self.assertEqual(self.run.call_args_list[0].args[0][-3:], ["Home;not-a-command", "password", "private-secret"])
        self.assertNotIn("private-secret", self.setup.progress.read_text())

    def test_display_block_is_idempotent_and_preserves_kernel(self):
        for rotation in ("90", "270"):
            self.setup.handle({"action": "display", "profile": "touch2-7", "rotation": rotation})
        text = (self.root / "boot/config.txt").read_text()
        self.assertEqual(text.count("# BEGIN PI HOME SETUP"), 1); self.assertIn("swapxy,invy", text)
        self.assertIn("kernel=vmlinuz-rpi", text)

    def test_invalid_zone_rotation_and_timezone_are_rejected(self):
        with self.assertRaises(ValueError): self.setup.handle({"action": "roon", "zone": "Missing"})
        with self.assertRaises(ValueError): self.setup.handle({"action": "display", "profile": "original", "rotation": "90"})
        with self.assertRaises(ValueError): self.setup.handle({"action": "display", "profile": "auto", "rotation": "normal", "timezone": "../etc/shadow"})

    def test_resume_and_completed_lock(self):
        self.setup.handle({"action": "name", "hostname": "pi-home"})
        resumed = module.Setup(self.root, self.run, lambda: {"zones": []})
        self.assertEqual(resumed.saved()["hostname"], "pi-home")
        self.setup.save({"complete": True})
        with self.assertRaises(ValueError): self.setup.handle({"action": "name", "hostname": "other"})
        self.assertTrue(self.setup.handle({"action": "status"})["progress"]["complete"])

    def test_symlink_read_is_refused(self):
        target = self.root / "outside"; target.write_text("secret")
        link = self.root / "link"; link.symlink_to(target)
        with self.assertRaises(OSError): module.read(link)


if __name__ == "__main__": unittest.main()
