import sys
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

from incidents import IncidentTracker


class IncidentTrackerTests(unittest.TestCase):

    def setUp(self):
        self.tracker = IncidentTracker(confirmations=2)
        self.tracker.update("healthy", "none", 100)
        self.tracker.update("healthy", "none", 110)

    def test_single_failure_not_confirmed(self):
        result = self.tracker.update(
            "critical", "tunnel_offline", 120
        )
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["raw_status"], "critical")

    def test_confirmed_failure(self):
        self.tracker.update(
            "critical", "tunnel_offline", 120
        )
        result = self.tracker.update(
            "critical", "tunnel_offline", 130
        )

        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["incident_count"], 1)

    def test_recovery(self):
        self.tracker.update(
            "critical", "tunnel_offline", 120
        )
        self.tracker.update(
            "critical", "tunnel_offline", 130
        )

        self.tracker.update("healthy", "none", 140)
        result = self.tracker.update(
            "healthy", "none", 150
        )

        self.assertEqual(result["status"], "healthy")
        self.assertEqual(
            result["last_incident_duration"], 20
        )
        self.assertEqual(result["mttr"], 20)

    def test_transient_failure(self):
        self.tracker.update(
            "critical", "website_unreachable", 120
        )
        result = self.tracker.update(
            "healthy", "none", 130
        )

        self.assertEqual(result["incident_count"], 0)

    def test_unknown_does_not_close_incident(self):
        self.tracker.update(
            "critical", "tunnel_offline", 120
        )
        self.tracker.update(
            "critical", "tunnel_offline", 130
        )
        self.tracker.update(
            "unknown", "metrics_unavailable", 140
        )
        result = self.tracker.update(
            "unknown", "metrics_unavailable", 150
        )

        self.assertEqual(result["status"], "unknown")
        self.assertIsNotNone(
            result["incident_started_at"]
        )


if __name__ == "__main__":
    unittest.main()
