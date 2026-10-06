import json
from pathlib import Path
import tomllib
import unittest

from pi_bus_time_display import __version__


class ReleaseVersionTests(unittest.TestCase):
    def test_displayed_and_packaged_versions_match(self):
        root = Path(__file__).resolve().parents[1]
        project = tomllib.loads((root / "pyproject.toml").read_text())
        package = json.loads((root / "roon-controller/package.json").read_text())
        lock = json.loads((root / "roon-controller/package-lock.json").read_text())
        for version in (project["project"]["version"], package["version"], lock["version"], lock["packages"][""]["version"]):
            self.assertEqual(version, __version__)
