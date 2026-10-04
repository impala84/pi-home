import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("alpine_updater", ROOT / "appliance/alpine/updater.py")
updater = importlib.util.module_from_spec(spec); spec.loader.exec_module(updater)


class AlpineUpdaterTests(unittest.TestCase):
    def test_only_successful_fixed_branch_builds_are_accepted(self):
        sha = "a" * 40
        valid = {"workflow_runs": [{"head_sha": sha, "head_branch": updater.BRANCH, "conclusion": "success", "event": "push", "head_repository": {"full_name": "impala84/pi-home"}}]}
        with patch.object(updater, "fetch_json", return_value=valid): self.assertEqual(updater.verified_revision(), sha)
        for changes in ({"head_sha": "../bad"}, {"head_branch": "main"}, {"conclusion": "failure"}, {"event": "pull_request"}, {"head_repository": {"full_name": "other/fork"}}):
            invalid = {"workflow_runs": [{**valid["workflow_runs"][0], **changes}]}
            with patch.object(updater, "fetch_json", return_value=invalid), self.assertRaises(RuntimeError): updater.verified_revision()

    def test_tar_traversal_and_links_are_rejected(self):
        for name, kind in (("../escape", tarfile.REGTYPE), ("repo/link", tarfile.SYMTYPE), ("/absolute", tarfile.REGTYPE)):
            with tempfile.TemporaryDirectory() as folder:
                archive = Path(folder) / "source.gz"
                with tarfile.open(archive, "w:gz") as tar:
                    item = tarfile.TarInfo(name); item.type = kind; item.linkname = "/etc/shadow"; tar.addfile(item)
                with self.assertRaises(RuntimeError): updater.extract_source(archive, Path(folder) / "out")

    def test_safe_source_extract_and_atomic_switch_back(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); archive = root / "source.gz"
            with tarfile.open(archive, "w:gz") as tar:
                item = tarfile.TarInfo("repo/appliance/alpine/updater.py"); item.size = 4; tar.addfile(item, io.BytesIO(b"pass"))
            source = updater.extract_source(archive, root / "out")
            self.assertTrue((source / "appliance/alpine/updater.py").exists())
            app = root / "pi-home"; old = root / "previous"; old.mkdir(); app.symlink_to(old)
            with patch.object(updater, "APP", app):
                updater.activate(source); self.assertEqual(app.resolve(), source.resolve())
                updater.activate(old); self.assertEqual(app.resolve(), old.resolve())

    def test_current_revision_does_not_download_or_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder); (app / ".source-commit").write_text("a" * 40)
            with patch.object(updater, "APP", app), patch.object(updater, "status"), patch.object(updater, "verified_revision", return_value="a" * 40), patch.object(updater, "restart") as restart:
                updater.update(); restart.assert_not_called()
