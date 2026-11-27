import sqlite3
import sys
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "src"
        / "infrastructure_ha_monitor"
    ),
)

from boot_tracker import BootTracker
from dynamic_edges import DynamicEdges

BOOT_A = "11111111-1111-4111-8111-111111111111"
BOOT_B = "22222222-2222-4222-8222-222222222222"


class BootTrackerTests(unittest.TestCase):

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.tracker = BootTracker(self.db)

    def tearDown(self):
        self.db.close()

    def test_initial_boot(self):
        self.tracker.observe("host", BOOT_A, 100)
        self.assertEqual(self.tracker.count("host"), 0)

    def test_repeated_boot(self):
        self.tracker.observe("host", BOOT_A, 100)
        self.tracker.observe("host", BOOT_A, 110)
        self.assertEqual(self.tracker.count("host"), 0)

    def test_reboot(self):
        self.tracker.observe("host", BOOT_A, 100)
        self.tracker.observe("host", BOOT_B, 110)
        self.assertEqual(self.tracker.count("host"), 1)

    def test_stale_snapshot(self):
        self.tracker.observe("host", BOOT_A, 100)
        self.tracker.observe("host", BOOT_B, 110)
        self.tracker.observe("host", BOOT_A, 105)
        self.assertEqual(self.tracker.count("host"), 1)

    def test_invalid_boot_id(self):
        self.tracker.observe("host", "invalid", 100)
        self.assertIsNone(self.tracker.count("host"))

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "boot.sqlite3"

            db = sqlite3.connect(path)
            tracker = BootTracker(db)
            tracker.observe("host", BOOT_A, 100)
            tracker.observe("host", BOOT_B, 110)
            db.close()

            db = sqlite3.connect(path)
            try:
                tracker = BootTracker(db)
                self.assertEqual(
                    tracker.count("host"), 1
                )
            finally:
                db.close()


class DynamicEdgeTests(unittest.TestCase):

    @patch("dynamic_edges.discover_edges")
    def test_address_filter_and_limit(self, discover):
        discover.return_value = [
            "198.41.192.47",
            "198.41.192.27",
            "198.41.192.47",
            "127.0.0.1",
            "192.168.1.1",
            "invalid",
        ]

        monitor = DynamicEdges(limit=1)

        self.assertEqual(
            monitor.targets(),
            ["198.41.192.27"],
        )

    @patch("dynamic_edges.discover_edges")
    def test_dns_cache(self, discover):
        discover.return_value = ["198.41.192.47"]

        monitor = DynamicEdges()

        monitor.targets()
        monitor.targets()

        discover.assert_called_once()

    @patch("dynamic_edges.discover_edges")
    def test_empty_discovery(self, discover):
        discover.return_value = []

        result = DynamicEdges().collect()

        self.assertEqual(result["total"], 0)
        self.assertIsNone(result["reachable"])


if __name__ == "__main__":
    unittest.main()
