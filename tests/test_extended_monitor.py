import sys
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "src"
        / "infrastructure_ha_monitor"
    ),
)

from extended_monitor import ExtendedMonitor


class ExtendedMonitorTests(unittest.TestCase):

    def setUp(self):
        self.monitor = ExtendedMonitor({
            "gateway": "192.0.2.1",
            "mounts": ["/"],
            "websites": ["https://example.invalid"],
            "tunnels": ["test"],
        })

    def test_registration(self):
        discovery = Mock()
        self.monitor.register(discovery)

        devices = {
            call.args[0]
            for call in discovery.call_args_list
        }

        self.assertIn("Host Diagnostics", devices)
        self.assertIn("Docker test", devices)
        self.assertIn("SSL example.invalid", devices)

    def test_cached_measurements(self):
        fn = Mock(return_value={"value": 42})
        state = Mock()

        with patch.object(
            self.monitor,
            "tasks",
            return_value=[
                ("Test", fn, (), 60, {"value": None})
            ],
        ):
            self.monitor.collect(state)
            self.monitor.collect(state)

        fn.assert_called_once()
        self.assertEqual(state.call_count, 2)

    def test_failed_probe(self):
        fn = Mock(side_effect=OSError("unavailable"))
        state = Mock()

        with patch.object(
            self.monitor,
            "tasks",
            return_value=[
                ("Test", fn, (), 60, {"value": None})
            ],
        ):
            self.monitor.collect(state)

        state.assert_called_once_with(
            "Test", "value", None
        )
