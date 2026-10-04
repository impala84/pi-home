import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("alpine_setup", ROOT / "appliance/alpine/setup_service.py")
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


class AlpineSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        config = self.root / "etc/pi-home"; config.mkdir(parents=True)
        (config / "config.toml").write_text((ROOT / "config.example.toml").read_text())
        (config / "secrets.env").write_text("ADMIN_PASSWORD=old\nADMIN_USERNAME=admin\n")
        boot = self.root / "boot"; (boot / "overlays").mkdir(parents=True)
        (boot / "config.txt").write_text("arm_64bit=1\ndisplay_auto_detect=1\nkernel=vmlinuz-rpi\n")
        for overlay in module.PROFILES.values():
            if overlay: (boot / "overlays" / (overlay + ".dtbo")).touch()
        self.run = Mock(return_value="connected")
        self.login_password = Mock()
        self.setup = module.Setup(self.root, self.run, lambda: {"zones": [{"name": "Lounge"}]}, self.login_password)

    def test_full_setup_persists_password_and_does_not_play_audio(self):
        self.setup.handle({"action": "name", "hostname": "Pi-Home-Lounge"})
        self.setup.handle({"action": "network"})
        self.setup.handle({"action": "roon", "zone": "Lounge"})
        self.setup.handle({"action": "display", "profile": "touch2-10", "rotation": "90", "timezone": "Europe/London", "theme": "roon"})
        self.setup.handle({"action": "finish", "password": "my-private-password", "confirmation": "my-private-password"})
        self.assertTrue(self.setup.saved()["complete"])
        self.assertEqual((self.root / "etc/hostname").read_text(), "pi-home-lounge\n")
        config = (self.root / "etc/pi-home/config.toml").read_text()
        self.assertIn('roon_zone_name = "Lounge"', config); self.assertIn('timezone = "Europe/London"', config)
        boot = (self.root / "boot/config.txt").read_text()
        self.assertIn("ili79600-10-1inch\n", boot); self.assertNotIn("swapxy", boot); self.assertIn("kernel=vmlinuz-rpi", boot)
        self.assertNotIn("password", self.setup.progress.read_text())
        env = self.root / "etc/pi-home/secrets.env"
        self.assertIn("ADMIN_PASSWORD=my-private-password", env.read_text()); self.assertEqual(env.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.run.call_args.args[0], ["rc-service", "pi-home-api", "restart"])
        self.login_password.assert_called_once_with("my-private-password")

    def test_invalid_names_never_execute_commands(self):
        for name in ("-bad", "bad-", "x;reboot", "a b", "../root", "x\n", "x" * 64):
            with self.assertRaises(ValueError): self.setup.handle({"action": "name", "hostname": name})
        self.run.assert_not_called()

    def test_password_minimum_is_eight_characters(self):
        module.validate_password("abcdefgh")
        with self.assertRaisesRegex(ValueError, "8–128"):
            module.validate_password("abcdefg")

    def test_tools_install_is_fixed_and_requires_completed_setup(self):
        with self.assertRaises(ValueError): self.setup.handle({"action": "install_tools"})
        self.setup.save({"complete": True})
        (self.root / "var/lib/pi-home").mkdir(parents=True, exist_ok=True)
        (self.root / "usr/local/bin").mkdir(parents=True, exist_ok=True)
        with patch.object(module.threading, "Thread") as thread:
            self.assertTrue(self.setup.handle({"action": "install_tools", "packages": ["untrusted"]})["queued"])
            self.assertFalse(self.setup.handle({"action": "install_tools"})["queued"])
            thread.assert_called_once()
        with patch.object(module.subprocess, "run", return_value=Mock(returncode=0)) as run:
            self.setup.install_tools()
            self.assertEqual(run.call_args.args[0], ["apk", "add", "--no-cache", "grim", "procps", "netdata", "netdata-openrc", "chrony", "chrony-openrc"])
        self.assertIn("installed", (self.root / "var/lib/pi-home/tools-status").read_text())
        self.assertFalse(self.setup.tools_lock.locked())

    def test_tools_install_failure_is_visible_and_retryable(self):
        (self.root / "var/lib/pi-home").mkdir(parents=True, exist_ok=True)
        self.setup.tools_lock.acquire()
        with patch.object(module.subprocess, "run", return_value=Mock(returncode=1)):
            self.setup.install_tools()
        self.assertIn("failed", (self.root / "var/lib/pi-home/tools-status").read_text())
        self.assertFalse(self.setup.tools_lock.locked())

    def test_transparent_cursor_theme_file(self):
        import struct
        spec = importlib.util.spec_from_file_location("cursor_theme", ROOT / "appliance/alpine/cursor_theme.py")
        cursor = importlib.util.module_from_spec(spec); spec.loader.exec_module(cursor)
        theme = cursor.prepare(self.root / "cursors")
        data = (theme / "cursors/left_ptr").read_bytes()
        self.assertEqual(struct.unpack("<4I", data[:16]), (0x72756358, 16, 0x10000, 1))
        self.assertEqual(len(data), 68)
        self.assertEqual(data[-4:], b"\0\0\0\0")

    def test_version_label_identifies_alpine_only(self):
        from pi_bus_time_display import server, __version__
        with patch.dict("os.environ", {"PI_HOME_APPLIANCE_PLATFORM": "alpine-prototype"}):
            self.assertEqual(server.display_version(), __version__ + " Alpine")
        with patch.dict("os.environ", {"PI_HOME_APPLIANCE_PLATFORM": ""}):
            self.assertEqual(server.display_version(), __version__)

    def test_incomplete_and_invalid_finishes_are_rejected(self):
        with self.assertRaises(ValueError): self.setup.handle({"action": "finish", "password": "valid-password"})
        self.assertFalse(self.setup.progress.exists())

    def test_failed_wifi_does_not_save_network_or_password(self):
        self.run.side_effect = ValueError("Connection failed")
        with self.assertRaises(ValueError): self.setup.handle({"action": "wifi", "ssid": "Home", "password": "secret"})
        self.assertFalse(self.setup.progress.exists())

    def test_failed_api_restart_leaves_finish_retryable(self):
        self.setup.save({"hostname": "pi-home", "network": True, "roon": True, "display": True})
        self.run.side_effect = ValueError("Service restart failed")
        with self.assertRaises(ValueError):
            self.setup.handle({"action": "finish", "password": "valid-password", "confirmation": "valid-password"})
        self.assertFalse(self.setup.saved().get("complete", False))
        self.run.side_effect = None
        self.setup.handle({"action": "finish", "password": "valid-password", "confirmation": "valid-password"})
        self.assertTrue(self.setup.saved()["complete"])

    def test_wifi_uses_argument_list_not_shell_and_keeps_secrets_out_of_progress(self):
        self.setup.handle({"action": "wifi", "ssid": "Home;not-a-command", "password": "private-secret"})
        self.assertEqual(self.run.call_args_list[0].args[0][-3:], ["Home;not-a-command", "password", "private-secret"])
        self.assertNotIn("private-secret", self.setup.progress.read_text())

    def test_display_block_is_idempotent_and_preserves_kernel(self):
        for rotation in ("90", "270"):
            self.setup.handle({"action": "display", "profile": "touch2-7", "rotation": rotation})
        text = (self.root / "boot/config.txt").read_text()
        self.assertEqual(text.count("# BEGIN PI HOME SETUP"), 1); self.assertNotIn("swapxy", text)
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

    def test_confirmation_and_ambiguous_passwords_are_rejected_before_changes(self):
        self.setup.save({"hostname": "pi-home", "network": True, "roon": True, "display": True})
        before = (self.root / "etc/pi-home/secrets.env").read_text()
        for password, confirmation in (("valid-password", "different-password"), (" valid-password", " valid-password"), ('"valid-password"', '"valid-password"')):
            with self.assertRaises(ValueError): self.setup.handle({"action": "finish", "password": password, "confirmation": confirmation})
        self.assertEqual(before, (self.root / "etc/pi-home/secrets.env").read_text())
        self.login_password.assert_not_called()

    def test_ssh_can_be_disabled_explicitly(self):
        self.setup.save({"hostname": "pi-home", "network": True, "roon": True, "display": True})
        self.setup.handle({"action": "finish", "password": "valid-password", "confirmation": "valid-password", "ssh": False})
        self.assertFalse(self.setup.saved()["ssh"])
        self.assertIn(unittest.mock.call(["rc-update", "del", "sshd", "default"]), self.run.call_args_list)

    def test_ssh_password_is_stdin_not_process_arguments(self):
        with patch.object(module.subprocess, "run", return_value=Mock(returncode=0)) as run:
            module.set_login_password("safe-private-password")
        self.assertEqual(run.call_args.args[0], ["chpasswd"])
        self.assertEqual(run.call_args.kwargs["input"], "admin:safe-private-password\n")

    def test_update_requires_completed_setup_and_uses_fixed_updater(self):
        with patch.object(module.subprocess, "Popen") as spawn:
            with self.assertRaises(ValueError): self.setup.handle({"action": "update"})
            spawn.assert_not_called()
            (self.root / "var/lib/pi-home").mkdir()
            self.setup.save({"complete": True})
            self.assertTrue(self.setup.handle({"action": "update"})["queued"])
            self.assertEqual(spawn.call_args.args[0], ["/usr/bin/python3", "/opt/pi-home/appliance/alpine/updater.py"])

    def test_netdata_controls_require_setup_and_use_only_fixed_openrc_commands(self):
        with self.assertRaises(ValueError): self.setup.handle({"action": "netdata_enable"})
        self.setup.save({"complete": True})
        with self.assertRaisesRegex(ValueError, "not installed"): self.setup.handle({"action": "netdata_enable"})
        service = self.root / "etc/init.d/netdata"; service.parent.mkdir(parents=True); service.touch()
        self.setup.handle({"action": "netdata_enable"})
        self.assertEqual(self.run.call_args.args[0], ["rc-service", "netdata", "start"])
        self.setup.handle({"action": "netdata_disable"})
        self.assertEqual(self.run.call_args.args[0], ["rc-update", "del", "netdata", "default"])

    def test_dsi_orientation_only_selects_current_dsi_mode(self):
        spec = importlib.util.spec_from_file_location("orientation", ROOT / "appliance/alpine/setup_orientation.py")
        orientation = importlib.util.module_from_spec(spec); spec.loader.exec_module(orientation)
        self.assertEqual(orientation.choose_output('HDMI-A-1 "HDMI"\n  1920x1080 px, 60 Hz (current)\nDSI-1 "DSI"\n  720x1280 px, 60 Hz (preferred, current)\n'), ("DSI-1", True))
        self.assertEqual(orientation.choose_output('HDMI-A-1 "HDMI"\n  720x1280 px, 60 Hz (current)\n'), (None, False))
        with patch.object(orientation.Path, "exists", return_value=False), patch.object(orientation.subprocess, "run", return_value=Mock(stdout='DSI-1 "DSI"\n  720x1280 px, 60 Hz (current)\n')) as run:
            orientation.main()
        self.assertEqual(run.call_args.args[0], ["wlr-randr", "--output", "DSI-1", "--transform", "normal"])

    def test_touch_mapping_is_scoped_to_goodix_and_one_connected_dsi(self):
        import sys
        spec = importlib.util.spec_from_file_location("input_mapping", ROOT / "appliance/alpine/input_mapping.py")
        mapping = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"setup_service": module}): spec.loader.exec_module(mapping)
        drm = self.root / "sys/class/drm"; drm.mkdir(parents=True)
        for name, status in (("card1-DSI-1", "connected"), ("card1-HDMI-A-1", "connected"), ("card2-DSI-2", "disconnected")):
            connector = drm / name; connector.mkdir(); (connector / "status").write_text(status)
        self.assertEqual(mapping.connected_output(self.root), "DSI-1")
        rule = mapping.mapping_rule("DSI-1")
        self.assertIn('ATTRS{name}=="*Goodix Capacitive TouchScreen"', rule)
        self.assertIn('ENV{WL_OUTPUT}=""', rule)
        self.assertIn('LIBINPUT_CALIBRATION_MATRIX}="1 0 0 0 1 0"', rule)
        self.assertIn('LIBINPUT_CALIBRATION_MATRIX}="0 1 0 -1 0 1"', mapping.mapping_rule("DSI-1", "90"))
        for rotation in mapping.MATRICES:
            values = [float(v) for v in mapping.MATRICES[rotation].split()]
            for x, y in ((0, 0), (0, 1), (1, 0), (1, 1)):
                result = (values[0]*x + values[1]*y + values[2], values[3]*x + values[4]*y + values[5])
                expected = {"normal": (x, y), "90": (y, 1-x), "180": (1-x, 1-y), "270": (1-y, x)}[rotation]
                self.assertEqual(result, expected)
        runner = Mock(return_value=Mock(returncode=0))
        self.assertFalse(mapping.recover_touch(self.root, runner, lambda _: None))
        runner.assert_not_called()
        node = self.root / "sys/bus/i2c/devices/10-005d/of_node"; node.mkdir(parents=True)
        (node / "compatible").write_bytes(b"goodix,gt911\0")
        name = self.root / "sys/class/input/event4/device/name"
        def recovered(args, **kwargs):
            if args == ["modprobe", "goodix_ts"]:
                name.parent.mkdir(parents=True); name.write_text("10-005d Goodix Capacitive TouchScreen\n")
            return Mock(returncode=0)
        runner.side_effect = recovered
        self.assertTrue(mapping.recover_touch(self.root, runner, lambda _: None))
        runner.reset_mock()
        self.assertTrue(mapping.recover_touch(self.root, runner, lambda _: None))
        runner.assert_not_called()
        name.unlink(); runner.side_effect = None
        self.assertFalse(mapping.recover_touch(self.root, runner, lambda _: None))
        self.assertEqual(sum(c.args[0] == ["modprobe", "goodix_ts"] for c in runner.call_args_list), 2)
        (drm / "card2-DSI-2/status").write_text("connected")
        self.assertIsNone(mapping.connected_output(self.root))
        with self.assertRaises(ValueError): mapping.mapping_rule('DSI-1", RUN+="bad')

    def test_orientation_is_first_and_does_not_complete_region(self):
        self.setup.handle({"action": "orientation", "profile": "touch2-7", "rotation": "90"})
        state = self.setup.saved()
        self.assertTrue(state["orientation"])
        self.assertNotIn("display", state)
        self.assertNotIn("timezone", state)
        self.assertIn("ili9881-7inch\n", (self.root / "boot/config.txt").read_text())
        with patch.object(module.threading, "Timer") as timer:
            self.assertTrue(self.setup.handle({"action": "reboot"})["ok"])
            timer.assert_called_once()

    def test_kernel_never_double_rotates_calibrated_touch(self):
        for rotation in ("normal", "90", "180", "270"):
            self.setup.handle({"action": "orientation", "profile": "touch2-7", "rotation": rotation})
            boot = (self.root / "boot/config.txt").read_text()
            self.assertIn("dtoverlay=vc4-kms-dsi-ili9881-7inch\n", boot)
            for flag in ("swapxy", "invx", "invy"): self.assertNotIn(flag, boot)


if __name__ == "__main__": unittest.main()
