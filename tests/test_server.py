import tempfile
import os
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from pi_bus_time_display.config import Config, load_config
from pi_bus_time_display.server import State, active_wifi_ssid, automatic_display_target, clear_sleep_mode_on_start, display_config_dir, display_orientation, display_target, home_assistant_set_state, home_assistant_set_value, netdata_snapshot, read_display_mode, service_state, set_display_mode, system_snapshot, within_sleep_window, write_config, write_control_request


class DisplayModeTests(unittest.TestCase):
    def test_display_orientation_is_derived_from_each_panels_native_shape(self):
        self.assertEqual(display_orientation("original", "normal"), "landscape")
        self.assertEqual(display_orientation("original", "90"), "portrait")
        self.assertEqual(display_orientation("touch2-10", "normal"), "portrait")
        self.assertEqual(display_orientation("touch2-10", "90"), "landscape")

    def test_alpine_display_settings_use_the_appliance_configuration(self):
        with patch.dict(os.environ, {"PI_HOME_APPLIANCE_PLATFORM": "alpine-prototype"}):
            self.assertEqual(display_config_dir(), Path("/etc/pi-home"))
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(display_config_dir(), Path("/etc/pi-bus-time-display"))

    def test_alpine_diagnostics_uses_openrc_service_names(self):
        from pi_bus_time_display.server import diagnostics_snapshot
        with patch.dict(os.environ, {"PI_HOME_APPLIANCE_PLATFORM": "alpine-prototype"}), patch("pi_bus_time_display.server.command_output", return_value=""), patch("pi_bus_time_display.server.service_state", return_value="running") as services:
            data = diagnostics_snapshot()
        self.assertTrue(all(process["active"] for process in data["processes"]))
        self.assertEqual({call.args[0] for call in services.call_args_list}, {"pi-home-roon", "pi-home-api", "pi-home-display", "roonbridge"})

    def test_bus_disabled_persists_and_automatic_stays_on_music(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            mode = Path(directory) / "mode"
            write_config(path, Config(bus_enabled=False))
            config = load_config(path)
            self.assertFalse(config.bus_enabled)
            state = State(config, Path(directory))
            self.assertFalse(state.snapshot()["bus_enabled"])
            noon = datetime(2026, 10, 4, 12, tzinfo=ZoneInfo(config.timezone))
            self.assertEqual(automatic_display_target(state, mode, {"zone": {"state": "paused"}}, noon), "http://127.0.0.1:8766/")
            self.assertEqual(display_target(config, mode, {"zone": {"state": "paused"}}, noon), "http://127.0.0.1:8766/")
            self.assertTrue(Config().bus_enabled)

    def test_display_theme_round_trip_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            self.assertEqual(Config().display_theme, "fresh-mint")
            write_config(path, Config(display_theme="roon"))
            self.assertEqual(load_config(path).display_theme, "roon")
            self.assertEqual(State(Config(display_theme="roon"), Path(directory)).snapshot()["display_theme"], "roon")
            write_config(path, Config(display_theme="invalid"))
            with self.assertRaises(ValueError): load_config(path)

    def test_custom_roon_display_name_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            write_config(path, Config(roon_display_name="Hi-Fi"))
            self.assertEqual(load_config(path).roon_display_name, "Hi-Fi")

    def test_custom_roon_view_names_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            write_config(path, Config(roon_now_playing_name="Roon", roon_queue_name="Q"))
            loaded = load_config(path)
            self.assertEqual(loaded.roon_now_playing_name, "Roon")
            self.assertEqual(loaded.roon_queue_name, "Q")

    def test_roon_browser_visibility_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            write_config(path, Config(roon_show_browser=False))
            self.assertFalse(load_config(path).roon_show_browser)

    def test_openobserve_settings_persist_without_a_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            write_config(path, Config(openobserve_enabled=True, openobserve_url="http://observe.local:5080", openobserve_username="admin"))
            loaded = load_config(path)
            self.assertTrue(loaded.openobserve_enabled)
            self.assertEqual(loaded.openobserve_url, "http://observe.local:5080")
            self.assertEqual(loaded.openobserve_username, "admin")
            self.assertNotIn("password", path.read_text(encoding="utf-8"))

    def test_system_summary_skips_diagnostics_unless_requested(self):
        with tempfile.TemporaryDirectory() as directory, patch("pi_bus_time_display.server.command_output", return_value=""), patch("pi_bus_time_display.server.diagnostics_snapshot", return_value={"checked": True}) as diagnostics:
            self.assertNotIn("diagnostics", system_snapshot(Path(directory)))
            self.assertEqual(system_snapshot(Path(directory), include_diagnostics=True)["diagnostics"], {"checked": True})
            diagnostics.assert_called_once_with()

    def test_system_summary_reports_same_boot_reboot_requirement(self):
        with tempfile.TemporaryDirectory() as directory, patch("pi_bus_time_display.server.command_output", return_value=""), patch("pi_bus_time_display.server.current_boot_id", return_value="test-boot"):
            state_dir = Path(directory)
            (state_dir / "reboot-required-boot-id").write_text("test-boot\n", encoding="ascii")
            self.assertTrue(system_snapshot(state_dir)["reboot_required"])

    def test_missing_mode_defaults_to_auto(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(read_display_mode(Path(directory) / "display-mode"), "auto")

    def test_valid_mode_is_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "display-mode"
            path.write_text("bus\n", encoding="utf-8")
            self.assertEqual(read_display_mode(path), "bus")

    def test_sleep_mode_is_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "display-mode"
            path.write_text("sleep\n", encoding="utf-8")
            self.assertEqual(read_display_mode(path), "sleep")

    def test_manual_sleep_is_cleared_when_service_starts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "display-mode"
            path.write_text("sleep\n", encoding="utf-8")
            clear_sleep_mode_on_start(path)
            self.assertEqual(read_display_mode(path), "auto")

    def test_visible_manual_mode_survives_service_start(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "display-mode"
            path.write_text("home\n", encoding="utf-8")
            clear_sleep_mode_on_start(path)
            self.assertEqual(read_display_mode(path), "home")

    def test_home_mode_targets_native_home_panel(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "display-mode"
            path.write_text("home\n", encoding="utf-8")
            self.assertEqual(display_target(Config(), path), "/home")

    def test_touchscreen_can_hide_a_configured_service(self):
        state = State(Config(services=("40", "42"), roon_display_name="Nowplay"))
        state.data = {"status": "ok", "services": [{"service": "40"}, {"service": "42"}]}
        state.enabled_services.discard("42")
        self.assertEqual([item["service"] for item in state.snapshot()["services"]], ["40"])
        self.assertEqual(state.snapshot()["roon_display_name"], "Nowplay")

    def test_touchscreen_bus_visibility_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            state = State(Config(services=("40", "42")), Path(directory))
            state.enabled_services.discard("42")
            state.save_enabled_services()
            restored = State(Config(services=("40", "42")), Path(directory))
            self.assertEqual(restored.enabled_services, {"40"})

    def test_display_brightness_is_clamped_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            state = State(Config(), Path(directory))
            state.save_display_brightness(3)
            self.assertEqual(state.display_brightness, 10)
            self.assertEqual(State(Config(), Path(directory)).display_brightness, 10)

    def test_netdata_state_comes_from_systemd(self):
        with patch("pi_bus_time_display.server.command_output", side_effect=["loaded", "active"]):
            self.assertEqual(service_state("netdata.service"), "running")
        with patch("pi_bus_time_display.server.command_output", side_effect=["not-found"]):
            self.assertEqual(service_state("netdata.service"), "not_installed")

    def test_netdata_state_uses_openrc_on_alpine(self):
        with patch.dict(os.environ, {"PI_HOME_APPLIANCE_PLATFORM": "alpine-prototype"}), patch("pi_bus_time_display.server.Path.is_file", return_value=True), patch("pi_bus_time_display.server.command_output", return_value=" * status: started") as command:
            self.assertEqual(service_state("netdata.service"), "running")
            command.assert_called_once_with(["rc-service", "netdata", "status"])
        with patch.dict(os.environ, {"PI_HOME_APPLIANCE_PLATFORM": "alpine-prototype"}), patch("pi_bus_time_display.server.Path.is_file", return_value=False):
            self.assertEqual(service_state("netdata.service"), "not_installed")

    def test_netdata_snapshot_reports_installed_version_and_cloud_state(self):
        with patch("pi_bus_time_display.server.service_state", return_value="running"), patch("pi_bus_time_display.server.urllib.request.urlopen", side_effect=OSError), patch("pi_bus_time_display.server.command_output", side_effect=["netdata v2.1.0", "Available: Yes\nClaimed: Yes\nClaimed Id: node-123\nOnline: Yes\n"]):
            details = netdata_snapshot()
        self.assertEqual(details["version"], "v2.1.0")
        self.assertEqual(details["cloud_status"], "online")
        self.assertEqual(details["claim_id"], "node-123")

    def test_unknown_mode_defaults_to_auto(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "display-mode"
            path.write_text("surprise\n", encoding="utf-8")
            self.assertEqual(read_display_mode(path), "auto")

    def test_roon_mode_targets_custom_controller(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "display-mode"
            path.write_text("roon\n", encoding="utf-8")
            self.assertEqual(display_target(Config(), path, {"zone": {"state": "playing"}}), "http://127.0.0.1:8766/")

    def test_roon_mode_uses_dark_fallback_when_controller_is_down(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "display-mode"
            path.write_text("roon\n", encoding="utf-8")
            self.assertEqual(display_target(Config(), path, None), "/roon-unavailable.html")

    def test_sleep_mode_targets_black_screen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "display-mode"
            path.write_text("sleep\n", encoding="utf-8")
            self.assertEqual(display_target(Config(), path), "/sleep.html")

    def test_overnight_sleep_window_crosses_midnight(self):
        config = Config(sleep_start="23:00", sleep_end="06:00")
        timezone = ZoneInfo("Asia/Singapore")
        self.assertTrue(within_sleep_window(config, datetime(2026, 9, 28, 23, 30, tzinfo=timezone)))
        self.assertTrue(within_sleep_window(config, datetime(2026, 9, 29, 5, 59, tzinfo=timezone)))
        self.assertFalse(within_sleep_window(config, datetime(2026, 9, 29, 6, 0, tzinfo=timezone)))

    def test_auto_sleeps_when_configured_zone_is_idle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "display-mode"
            path.write_text("auto\n", encoding="utf-8")
            config = Config(sleep_when_roon_idle=True)
            evening = datetime(2026, 9, 28, 20, 0, tzinfo=ZoneInfo("Asia/Singapore"))
            self.assertEqual(display_target(config, path, {"zone": {"state": "paused"}}, evening), "/sleep.html")
            self.assertEqual(display_target(config, path, {"zone": {"state": "playing"}}, evening), "http://127.0.0.1:8766/")

    def test_touchscreen_update_request_is_atomically_queued(self):
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory)
            self.assertTrue(write_control_request(state_dir, {"action": "update"}))
            requests = list((state_dir / "system-action-queue").glob("*.json"))
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0].read_text(encoding="utf-8"), '{"action": "update"}')
            self.assertTrue((state_dir / "system-action-trigger").read_text(encoding="ascii").strip())
            self.assertFalse(list((state_dir / "system-action-queue").glob("*.tmp")))
            self.assertEqual((state_dir / "update-status").read_text(encoding="utf-8"), "Update · Queued…\n")

    def test_duplicate_update_request_is_not_queued(self):
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory)
            self.assertTrue(write_control_request(state_dir, {"action": "update"}))
            self.assertFalse(write_control_request(state_dir, {"action": "update"}))
            self.assertEqual(len(list((state_dir / "system-action-queue").glob("*.json"))), 1)

    def test_quick_privileged_actions_do_not_overwrite_each_other(self):
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory)
            write_control_request(state_dir, {"action": "display_off"})
            write_control_request(state_dir, {"action": "display_on", "brightness": 63})
            requests = sorted((state_dir / "system-action-queue").glob("*.json"))
            self.assertEqual(len(requests), 2)
            self.assertEqual(
                [path.read_text(encoding="utf-8") for path in requests],
                ['{"action": "display_off"}', '{"action": "display_on", "brightness": 63}'],
            )

    def test_playback_temporarily_takes_over_automatic_bus_display(self):
        with tempfile.TemporaryDirectory() as directory:
            mode = Path(directory) / "display-mode"
            mode.write_text("auto\n", encoding="utf-8")
            state = State(Config(auto_switch_to_roon=True, roon_idle_return_seconds=300))
            morning = datetime(2026, 9, 29, 8, 0, tzinfo=ZoneInfo("Asia/Singapore"))
            with patch("pi_bus_time_display.server.time.monotonic", return_value=1000):
                self.assertEqual(automatic_display_target(state, mode, {"zone": {"state": "playing"}}, morning), "http://127.0.0.1:8766/")
            with patch("pi_bus_time_display.server.time.monotonic", return_value=1200):
                self.assertEqual(automatic_display_target(state, mode, {"zone": {"state": "paused"}}, morning), "http://127.0.0.1:8766/")
            with patch("pi_bus_time_display.server.time.monotonic", return_value=1400):
                self.assertEqual(automatic_display_target(state, mode, {"zone": {"state": "paused"}}, morning), "/")

    def test_active_playback_keeps_automatic_display_on_even_overnight(self):
        with tempfile.TemporaryDirectory() as directory:
            mode = Path(directory) / "display-mode"
            mode.write_text("auto\n", encoding="utf-8")
            state = State(Config(auto_switch_to_roon=False))
            overnight = datetime(2026, 9, 29, 1, 0, tzinfo=ZoneInfo("Asia/Singapore"))
            self.assertEqual(automatic_display_target(state, mode, {"zone": {"state": "playing"}}, overnight), "http://127.0.0.1:8766/")
            self.assertEqual(automatic_display_target(state, mode, {"zone": {"state": "paused"}}, overnight), "/sleep.html")

    def test_temporary_wake_expires_during_sleep_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            mode = Path(directory) / "display-mode"
            mode.write_text("auto\n", encoding="utf-8")
            state = State(Config(outside_hours_wake_seconds=600))
            overnight = datetime(2026, 9, 29, 1, 0, tzinfo=ZoneInfo("Asia/Singapore"))
            state.awake_until = 1600
            with patch("pi_bus_time_display.server.time.monotonic", return_value=1200):
                self.assertEqual(automatic_display_target(state, mode, {"zone": {"state": "paused"}}, overnight), "/")
            with patch("pi_bus_time_display.server.time.monotonic", return_value=1700):
                self.assertEqual(automatic_display_target(state, mode, {"zone": {"state": "paused"}}, overnight), "/sleep.html")

    def test_manual_view_returns_to_automatic_at_next_schedule_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            mode = Path(directory) / "display-mode"
            mode.write_text("home\n", encoding="utf-8")
            state = State(Config(morning_start="07:00", morning_end="09:30", sleep_start="22:00", sleep_end="07:00"))
            state.manual_mode_signature = (mode.stat().st_mtime_ns, "home")
            state.manual_mode_period = "morning"
            morning = datetime(2026, 9, 29, 8, 0, tzinfo=ZoneInfo("Asia/Singapore"))
            daytime = datetime(2026, 9, 29, 9, 30, tzinfo=ZoneInfo("Asia/Singapore"))
            self.assertEqual(automatic_display_target(state, mode, None, morning), "/home")
            self.assertEqual(automatic_display_target(state, mode, None, daytime), "/")
            self.assertEqual(read_display_mode(mode), "auto")

    def test_manual_sleep_returns_to_automatic_at_morning_wake(self):
        with tempfile.TemporaryDirectory() as directory:
            mode = Path(directory) / "display-mode"
            mode.write_text("sleep\n", encoding="utf-8")
            state = State(Config(morning_start="07:00", morning_end="09:30", sleep_start="22:00", sleep_end="07:00"))
            state.manual_mode_signature = (mode.stat().st_mtime_ns, "sleep")
            state.manual_mode_period = "sleep"
            morning = datetime(2026, 9, 29, 7, 0, tzinfo=ZoneInfo("Asia/Singapore"))
            self.assertEqual(automatic_display_target(state, mode, None, morning), "/")
            self.assertEqual(read_display_mode(mode), "auto")

    def test_touch_can_temporarily_wake_a_manual_sleep_before_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            mode = Path(directory) / "display-mode"
            mode.write_text("sleep\n", encoding="utf-8")
            state = State(Config(sleep_start="22:00", sleep_end="07:00"))
            state.manual_mode_signature = (mode.stat().st_mtime_ns, "sleep")
            state.manual_mode_period = "sleep"
            state.awake_until = 1600
            overnight = datetime(2026, 9, 29, 1, 0, tzinfo=ZoneInfo("Asia/Singapore"))
            with patch("pi_bus_time_display.server.time.monotonic", return_value=1200):
                self.assertEqual(automatic_display_target(state, mode, None, overnight), "/")

    def test_explicit_sleep_cancels_a_temporary_wake(self):
        with tempfile.TemporaryDirectory() as directory:
            mode = Path(directory) / "display-mode"
            state = State(Config(sleep_start="22:00", sleep_end="07:00"))
            state.awake_until = 1600
            set_display_mode(state, mode, "sleep")
            self.assertEqual(state.awake_until, 0.0)
            overnight = datetime(2026, 9, 29, 1, 0, tzinfo=ZoneInfo("Asia/Singapore"))
            with patch("pi_bus_time_display.server.time.monotonic", return_value=1200):
                self.assertEqual(automatic_display_target(state, mode, None, overnight), "/sleep.html")

    def test_wifi_reports_ssid_not_netplan_profile_name(self):
        with patch("pi_bus_time_display.server.command_output", side_effect=["netplan-wlan0-Boogaloo:802-11-wireless", "Boogaloo"]):
            self.assertEqual(active_wifi_ssid(), "Boogaloo")

    def test_home_light_level_uses_brightness_percentage(self):
        with patch("pi_bus_time_display.server.home_assistant_request", return_value=[]) as request:
            home_assistant_set_value(Config(), "light.living_room", 63)
            request.assert_called_once_with(Config(), "/api/services/light/turn_on", {"entity_id": "light.living_room", "brightness_pct": 63})

    def test_home_fan_level_is_clamped(self):
        with patch("pi_bus_time_display.server.home_assistant_request", return_value=[]) as request:
            home_assistant_set_value(Config(), "fan.living_room", 140)
            request.assert_called_once_with(Config(), "/api/services/fan/set_percentage", {"entity_id": "fan.living_room", "percentage": 100})

    def test_home_switch_swipe_sets_explicit_state(self):
        with patch("pi_bus_time_display.server.home_assistant_request", return_value=[]) as request:
            home_assistant_set_state(Config(), "switch.pi_hole", False)
            request.assert_called_once_with(Config(), "/api/services/switch/turn_off", {"entity_id": "switch.pi_hole"})


if __name__ == "__main__":
    unittest.main()
