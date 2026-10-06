import importlib.machinery
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "pi-bus-system-action"


def load_helper():
    loader = importlib.machinery.SourceFileLoader("pi_bus_system_action", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class SystemActionQueueTests(unittest.TestCase):
    def test_display_apply_persists_mounting_and_reboots_automatically(self):
        helper = load_helper()
        with tempfile.TemporaryDirectory() as directory, patch.object(helper, 'DISPLAY_CONFIG', Path(directory)), patch.object(helper, 'run') as run, patch.object(helper, 'report'):
            helper.execute({'action': 'set_display', 'profile': 'touch2-10', 'orientation': 'portrait', 'mounting': 'inverted'})
            self.assertEqual((Path(directory) / 'display-mounting').read_text(), 'inverted\n')
            self.assertEqual([call.args[0] for call in run.call_args_list], [
                ['/usr/local/sbin/pi-bus-appliance-mode', 'display', 'touch2-10', '180'], ['systemctl', 'reboot']])

    def test_roon_install_uses_fixed_official_installer(self):
        helper = load_helper()
        with patch.object(helper, 'run') as run, patch.object(helper, 'report'):
            helper.execute({'action': 'roon_install'})
        run.assert_called_once_with(['/bin/bash', str(helper.APP / 'scripts/install-roon-bridge.sh')])

    def test_lightweight_restarts_only_running_agent(self):
        helper = load_helper()
        for active in (0, 3):
            with patch.object(helper.subprocess, 'run', side_effect=[type('Result', (), {'returncode': 0})(), type('Result', (), {'returncode': active})()]), patch.object(helper, 'run') as run, patch.object(helper, 'report'), patch.object(helper, 'configure_netdata_lightweight') as configure:
                helper.execute({'action': 'netdata_lightweight', 'enabled': True})
                configure.assert_called_once_with(Path('/'), True)
                self.assertEqual(run.call_count, 1 if active == 0 else 0)

    def test_official_install_never_executes_or_logs_pasted_shell(self):
        helper = load_helper()
        pasted = 'bash <(curl -Ss https://get.netdata.cloud/kickstart.sh) --claim-token private-token --claim-rooms room-1234 ; touch /tmp/unsafe'
        with tempfile.TemporaryDirectory() as directory, patch.object(helper, 'STATE', Path(directory)), patch.object(helper, 'run') as run, patch.object(helper, 'configure_netdata_lightweight'), patch.object(helper.urllib.request, 'urlopen') as response, patch.object(helper.subprocess, 'run', return_value=type('Result', (), {'returncode': 0})()) as process:
            response.return_value.__enter__.return_value.read.return_value = b'# official test installer'
            helper.install_netdata(pasted)
            arguments = process.call_args.args[0]
            self.assertIn('--stable-channel', arguments)
            self.assertIn('--auto-update', arguments)
            self.assertNotIn(pasted, arguments)
            self.assertNotIn('touch', arguments)
            self.assertNotIn('private-token', repr(run.call_args_list))
            self.assertNotIn('private-token', (Path(directory) / 'netdata-operation-status').read_text())
            self.assertFalse(Path(arguments[1]).exists())

    def test_install_timeout_does_not_expose_claim_token(self):
        helper = load_helper()
        pasted = 'bash <(curl -Ss https://get.netdata.cloud/kickstart.sh) --claim-token private-token'
        with tempfile.TemporaryDirectory() as directory, patch.object(helper, 'STATE', Path(directory)), patch.object(helper, 'run'), patch.object(helper.urllib.request, 'urlopen') as response, patch.object(helper.subprocess, 'run', side_effect=helper.subprocess.TimeoutExpired(['bash', '--claim-token', 'private-token'], 900)):
            response.return_value.__enter__.return_value.read.return_value = b'# official test installer'
            with self.assertRaises(RuntimeError) as error: helper.install_netdata(pasted)
            self.assertNotIn('private-token', str(error.exception))

    def test_reboot_uses_only_the_fixed_systemd_action(self):
        helper = load_helper()
        with patch.object(helper, "run") as run, patch.object(helper, "report") as report:
            helper.execute({"action": "reboot"})
        report.assert_any_call("Reboot requested. Pi Home is restarting…")
        run.assert_called_once_with(["systemctl", "reboot"])

    def test_failed_update_gets_a_dedicated_terminal_status(self):
        helper = load_helper()
        with patch.object(helper, "run", side_effect=RuntimeError("download failed")), patch.object(helper, "report"), patch.object(helper, "report_update") as report_update:
            with self.assertRaisesRegex(RuntimeError, "download failed"):
                helper.execute({"action": "update"})
        self.assertEqual(report_update.call_args_list[-1].args[0], "Failed: download failed")

    def test_drains_requests_in_order(self):
        helper = load_helper()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            queue = state / "system-action-queue"
            queue.mkdir()
            (queue / "0002.json").write_text(json.dumps({"action": "display_on"}), encoding="utf-8")
            (queue / "0001.json").write_text(json.dumps({"action": "display_off"}), encoding="utf-8")
            with patch.object(helper, "STATE", state), patch.object(helper, "REQUEST", state / "legacy.json"), patch.object(helper, "QUEUE", queue), patch.object(helper, "STATUS", state / "status"), patch.object(helper, "execute") as execute:
                helper.main()
            self.assertEqual([call.args[0]["action"] for call in execute.call_args_list], ["display_off", "display_on"])
            self.assertFalse(list(queue.glob("*.json")))

    def test_failed_request_does_not_strand_later_wake(self):
        helper = load_helper()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            queue = state / "system-action-queue"
            queue.mkdir()
            (queue / "0001.json").write_text(json.dumps({"action": "bad"}), encoding="utf-8")
            (queue / "0002.json").write_text(json.dumps({"action": "display_on"}), encoding="utf-8")
            seen = []

            def execute(data):
                seen.append(data["action"])
                if data["action"] == "bad":
                    raise ValueError("broken request")

            with patch.object(helper, "STATE", state), patch.object(helper, "REQUEST", state / "legacy.json"), patch.object(helper, "QUEUE", queue), patch.object(helper, "STATUS", state / "status"), patch.object(helper, "execute", side_effect=execute):
                helper.main()
            self.assertEqual(seen, ["bad", "display_on"])
            self.assertFalse(list(queue.glob("*.json")))

    def test_collapses_update_requests_left_by_an_older_release(self):
        helper = load_helper()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            queue = state / "system-action-queue"
            queue.mkdir()
            (queue / "0001.json").write_text(json.dumps({"action": "update"}), encoding="utf-8")
            (queue / "0002.json").write_text(json.dumps({"action": "update"}), encoding="utf-8")
            (queue / "0003.json").write_text(json.dumps({"action": "display_on"}), encoding="utf-8")
            with patch.object(helper, "STATE", state), patch.object(helper, "REQUEST", state / "legacy.json"), patch.object(helper, "QUEUE", queue), patch.object(helper, "STATUS", state / "status"), patch.object(helper, "execute") as execute:
                helper.main()
            self.assertEqual([call.args[0]["action"] for call in execute.call_args_list], ["update", "display_on"])
            self.assertFalse(list(queue.glob("*.json")))


if __name__ == "__main__":
    unittest.main()
