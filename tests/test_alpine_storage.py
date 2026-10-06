import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("alpine_expand_root", ROOT / "appliance/alpine/expand_root.py")
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)


def fake_sysfs(root: Path, disk_sectors=62_000_000, partition_sectors=3_670_016):
    disk = root / "devices/platform/mmc/block/mmcblk0"
    part = disk / "mmcblk0p2"
    part.mkdir(parents=True)
    (disk / "size").write_text(str(disk_sectors))
    (part / "partition").write_text("2")
    (part / "start").write_text("526336")
    (part / "size").write_text(str(partition_sectors))
    links = root / "dev-block"; links.mkdir()
    (links / "179:2").symlink_to(part)
    return links


class AlpineStorageTests(unittest.TestCase):
    def test_discovers_root_disk_partition_and_remaining_space_from_sysfs(self):
        with tempfile.TemporaryDirectory() as folder:
            links = fake_sysfs(Path(folder))
            disk, part, number, unused = storage.root_partition(links, (179, 2))
        self.assertEqual((disk, part, number), (Path("/dev/mmcblk0"), Path("/dev/mmcblk0p2"), 2))
        self.assertGreater(unused, 20_000_000_000)

    def test_first_run_grows_partition_then_filesystem_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); state = root / "state"; log = root / "storage.log"
            links = fake_sysfs(root)
            with patch.object(storage, "root_filesystem_type", return_value="ext4"), patch.object(storage, "run") as run:
                self.assertEqual(storage.expand(state, log, links, (179, 2)), "expanded")
                self.assertEqual(storage.expand(state, log, links, (179, 2)), "already completed")
            self.assertEqual([call.args[0] for call in run.call_args_list], [
                ["/usr/bin/growpart", "/dev/mmcblk0", "2"],
                ["/usr/sbin/resize2fs", "/dev/mmcblk0p2"],
            ])
            self.assertTrue((state / "root-storage-expanded").exists())
            self.assertIn("completed", log.read_text())

    def test_full_partition_still_checks_filesystem_for_interrupted_previous_boot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); links = fake_sysfs(root, disk_sectors=4_196_500)
            with patch.object(storage, "root_filesystem_type", return_value="ext4"), patch.object(storage, "run") as run:
                self.assertEqual(storage.expand(root / "state", root / "log", links, (179, 2)), "filesystem checked")
            run.assert_called_once_with(["/usr/sbin/resize2fs", "/dev/mmcblk0p2"], root / "log")

    def test_failure_is_logged_without_marking_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); links = fake_sysfs(root)
            with patch.object(storage, "STATE", root / "state"), patch.object(storage, "LOG", root / "log"), patch.object(storage, "SYS_DEV_BLOCK", links), patch.object(storage, "root_filesystem_type", return_value="ext4"), patch.object(storage, "run", side_effect=RuntimeError("simulated failure")):
                self.assertEqual(storage.main(), 1)
            self.assertFalse((root / "state/root-storage-expanded").exists())
            self.assertIn("failed safely", (root / "log").read_text())

    def test_non_partition_root_is_rejected_safely(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); device = root / "devices/dm-0"; device.mkdir(parents=True)
            links = root / "links"; links.mkdir(); (links / "253:0").symlink_to(device)
            with self.assertRaisesRegex(RuntimeError, "not on a directly growable"):
                storage.root_partition(links, (253, 0))


if __name__ == "__main__":
    unittest.main()
