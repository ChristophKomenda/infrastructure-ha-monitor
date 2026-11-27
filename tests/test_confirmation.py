import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "src"
        / "infrastructure_ha_monitor"
    ),
)

from confirmation import Confirmation
from mqtt_security import configure_tls


class ConfirmationTests(unittest.TestCase):

    def setUp(self):
        self.engine = Confirmation(2)

    def test_duplicates(self):
        for _ in range(10):
            result = self.engine.update(
                "critical", "wan", (100, 101)
            )

        self.assertEqual(result[0], "unknown")

    def test_new_snapshots(self):
        self.engine.update(
            "critical", "wan", (100, 101)
        )

        self.assertEqual(
            self.engine.update(
                "critical", "wan", (110, 111)
            ),
            ("critical", "wan"),
        )

    def test_single_agent_update(self):
        self.engine.update(
            "critical", "wan", (100, 101)
        )

        result = self.engine.update(
            "critical", "wan", (110, 101)
        )

        self.assertEqual(result[0], "unknown")

    def test_unknown_resets_candidate(self):
        self.engine.update(
            "critical", "wan", (100, 101)
        )
        self.engine.update("unknown", "stale", ())

        result = self.engine.update(
            "critical", "wan", (110, 111)
        )

        self.assertEqual(result[0], "unknown")

    def test_recovery(self):
        self.engine.update(
            "critical", "wan", (100, 101)
        )
        self.engine.update(
            "critical", "wan", (110, 111)
        )
        result = self.engine.update(
            "healthy", "none", (120, 121)
        )
        self.assertEqual(result[0], "unknown")

        result = self.engine.update(
            "healthy", "none", (130, 131)
        )
        self.assertEqual(result[0], "healthy")


class TLSTests(unittest.TestCase):

    def test_disabled(self):
        client = Mock()
        configure_tls(client, {"tls": False})
        client.tls_set_context.assert_not_called()

    def test_enabled(self):
        client = Mock()
        configure_tls(client, {"tls": True})
        context = client.tls_set_context.call_args.args[0]
        self.assertTrue(context.check_hostname)

    def test_insecure_rejected(self):
        with self.assertRaises(ValueError):
            configure_tls(
                Mock(),
                {"tls": True, "tls_insecure": True},
            )
