import importlib.util
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('haos_run', ROOT / 'haos/run.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PackageTests(unittest.TestCase):
    def options(self):
        return dict(primary_node='primary', secondary_node='secondary', mqtt_host='broker', mqtt_port=8883, mqtt_username='user', mqtt_password='secret', mqtt_tls=True)

    def test_config(self):
        cfg = module.build_config(self.options())
        self.assertEqual(cfg['correlation_nodes'], ['primary', 'secondary'])
        self.assertTrue(cfg['mqtt']['tls'])

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            module.build_config(dict(self.options(), secondary_node='primary'))

    def test_empty_password(self):
        with self.assertRaises(ValueError):
            module.build_config(dict(self.options(), mqtt_password=''))

    def test_source_copy(self):
        for path in (ROOT / 'src').rglob('*.py'):
            self.assertEqual(path.read_bytes(), (ROOT / 'haos' / path.relative_to(ROOT)).read_bytes())
