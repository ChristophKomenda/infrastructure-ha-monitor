import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "src"
        / "infrastructure_ha_monitor"
    ),
)

from storage import History


class StorageTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = (
            Path(self.directory.name) / "test.sqlite3"
        )
        self.history = History(self.path)

    def tearDown(self):
        self.history.close()
        self.directory.cleanup()

    def test_persistent_incident(self):
        self.history.record("critical", "failure", 100)
        self.history.record("healthy", "none", 110)

        self.history.close()
        self.history = History(self.path)

        stats = self.history.statistics(120)

        self.assertEqual(stats["incident_count"], 1)
        self.assertEqual(stats["mttr"], 10)

    def test_unknown_not_available(self):
        self.history.record("unknown", "missing", 100)

        stats = self.history.availability(1, 110)

        self.assertIsNone(stats["uptime"])
        self.assertEqual(stats["coverage"], 0)

    def test_availability(self):
        self.history.record("healthy", "none", 100)
        self.history.record("critical", "failure", 110)

        stats = self.history.availability(1, 120)

        self.assertEqual(stats["uptime"], 50)

    def test_degraded_availability(self):
        self.history.record(
            "degraded", "redundancy", 100
        )

        stats = self.history.availability(1, 110)

        self.assertEqual(stats["uptime"], 100)
        self.assertEqual(stats["healthy"], 0)

    def test_no_duplicate_incidents(self):
        self.history.record("critical", "failure", 100)
        self.history.record("degraded", "partial", 110)

        self.assertEqual(
            self.history.statistics(120)["incident_count"],
            1
        )

    def test_unknown_interrupts_incident(self):
        self.history.record("critical", "failure", 100)
        self.history.record("unknown", "missing", 110)

        stats = self.history.statistics(120)

        self.assertEqual(stats["completed_incidents"], 0)
        self.assertIsNone(stats["mttr"])

    def test_gap_not_counted_as_recovery(self):
        self.history.record("critical", "failure", 100)
        self.history.record("healthy", "none", 1000)

        self.assertIsNone(
            self.history.statistics(1000)["mttr"]
        )

    def test_cleanup(self):
        self.history.record("healthy", "none", 100)

        self.history.cleanup(
            retention_days=1,
            now=100000,
        )

        count = self.history.db.execute(
            "SELECT COUNT(*) FROM samples"
        ).fetchone()[0]

        self.assertEqual(count, 0)



    def test_short_unknown_preserves_incident(self):
        self.history.record("critical", "wan", 100)
        self.history.record("unknown", "pending", 105)
        self.history.record("critical", "wan", 110)

        stats = self.history.statistics(115)

        self.assertEqual(stats["incident_count"], 1)
        self.assertEqual(stats["active_incident_duration"], 15)

    def test_mtbf(self):
        self.history.record("critical", "wan", 100)
        self.history.record("healthy", "none", 110)
        self.history.record("healthy", "none", 120)
        self.history.record("healthy", "none", 130)
        self.history.record("critical", "wan", 140)

        self.assertEqual(
            self.history.calculate_mtbf(150), 30
        )

    def test_mtbf_excludes_unknown(self):
        self.history.record("critical", "wan", 100)
        self.history.record("healthy", "none", 110)
        self.history.record("unknown", "missing", 120)
        self.history.record("healthy", "none", 130)
        self.history.record("critical", "wan", 140)

        self.assertIsNone(
            self.history.calculate_mtbf(150)
        )


if __name__ == "__main__":
    unittest.main()
