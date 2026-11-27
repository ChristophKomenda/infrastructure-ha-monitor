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

from confirmation import Confirmation
from storage import History


class IncidentLifecycleTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.history = History(
            Path(self.temp.name) / "test.sqlite3"
        )
        self.tracker = Confirmation(confirmations=2)

    def tearDown(self):
        self.history.close()
        self.temp.cleanup()

    def sample(self, timestamp, status, diagnosis):
        confirmed_status, confirmed_diagnosis = (
            self.tracker.update(
                status,
                diagnosis,
                (timestamp, timestamp),
            )
        )

        # Pending confirmation is not missing telemetry.
        if confirmed_diagnosis == "confirmation_pending":
            confirmed_status = "pending"

        self.history.record(
            confirmed_status,
            confirmed_diagnosis,
            timestamp,
        )

    def test_confirmed_incident_recovery(self):
        self.sample(100, "healthy", "none")
        self.sample(110, "healthy", "none")

        self.sample(120, "critical", "wan_failure")
        self.sample(130, "critical", "wan_failure")
        self.sample(140, "critical", "wan_failure")

        self.sample(150, "healthy", "none")
        self.sample(160, "healthy", "none")

        stats = self.history.statistics(160)

        self.assertEqual(stats["incident_count"], 1)
        self.assertEqual(stats["completed_incidents"], 1)
        self.assertEqual(stats["mttr"], 30)


if __name__ == "__main__":
    unittest.main()
