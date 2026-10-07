"""The source, web component and appliance vectors must remain one family."""
import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('icon_catalog', ROOT / 'tools/build_icons.py')
catalog = importlib.util.module_from_spec(spec); spec.loader.exec_module(catalog)

class IconFamilyTests(unittest.TestCase):
    def test_generated_assets_are_current(self):
        for name, content in catalog.outputs().items():
            self.assertEqual((ROOT / name).read_text(), content, name)

    def test_every_vector_has_shared_rules_and_safe_geometry(self):
        for name in catalog.ICONS:
            root = ET.fromstring(catalog.svg(name))
            self.assertEqual(root.get('viewBox'), '0 0 64 64', name)
            self.assertEqual(root.get('stroke'), 'currentColor', name)
            self.assertEqual(root.get('stroke-width'), '2', name)
            self.assertEqual(root.get('fill'), 'none', name)
            self.assertEqual(root.get('stroke-linecap'), 'round', name)
            self.assertEqual(root.get('stroke-linejoin'), 'round', name)
            self.assertGreater(len(list(root)), 0, name)
            for child in root:
                self.assertIn(child.tag.split('}')[-1], ('path', 'circle', 'ellipse', 'rect'), name)

    def test_all_final_genres_and_controls_exist(self):
        for name in ('rock classical electronic jazz stage world vocal blues easy rb rap avant folk ambient reggae country latin religious holiday children comedy album artist music playlist search play pause previous next add remove heart settings fan light switch brightness orientation clock home bus discover back forward overflow power check'.split()):
            self.assertIn(name, catalog.ICONS)
        self.assertNotEqual(catalog.ICONS['blues'], catalog.ICONS['jazz'])
        self.assertNotEqual(catalog.ICONS['reggae'], catalog.ICONS['world'])
