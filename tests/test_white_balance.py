import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('white_balance', Path(__file__).resolve().parents[1] / 'native-display/white_balance.py')
balance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(balance)

class WhiteBalanceTests(unittest.TestCase):
    def test_missing_profile_preserves_colours(self):
        self.assertEqual(balance.read_gains('/nonexistent/pi-home-colour.json'), balance.IDENTITY)

    def test_profile_is_per_device_and_read_without_modification(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'profile.json'
            data = json.dumps({'rgb_gains': [0.9665, 0.8712, 1.0]})
            path.write_text(data)
            self.assertEqual(balance.read_gains(path), (0.9665, 0.8712, 1.0))
            self.assertEqual(path.read_text(), data)

    def test_malformed_and_blackout_profiles_fall_back(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'profile.json'
            for data in ('invalid', '{}', '[]', '{"rgb_gains": [0, 0, 0]}', '{"rgb_gains": [1, 1]}', '{"rgb_gains": [true, 1, 1]}', '{"rgb_gains": [NaN, 1, 1]}', '{"rgb_gains": [1.2, 1, 1]}', ' ' * 4097):
                path.write_text(data)
                self.assertEqual(balance.read_gains(path), balance.IDENTITY)

    def test_matrix_preserves_alpha_and_does_not_mix_channels(self):
        gains = (.9665, .8712, 1.0)
        matrix = balance.gain_matrix(gains)
        self.assertEqual([matrix[n] for n in (0,5,10,15)], [*gains,1])
        self.assertTrue(all(matrix[n] == 0 for n in range(16) if n not in (0,5,10,15)))
