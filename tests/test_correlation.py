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

from correlation import correlate, NODES


class CorrelationTests(unittest.TestCase):

    def setUp(self):
        self.snapshots = {}

        for node in NODES:
            self.snapshots[node] = {
                "schema_version": 1,
                "node_id": node,
                "timestamp": 1000,
                "status": "healthy",
                "data": {
                    "network": {
                        "gateway": True,
                        "google": True,
                        "cloudflare": True,
                    },
                    "cloudflare_edge": {
                        "reachable": 4,
                        "total": 4,
                    },
                },
            }

        self.availability = {
            node: "online" for node in NODES
        }

    def diagnose(self):
        return correlate(
            self.snapshots,
            self.availability,
            now=1005,
        )["diagnosis"]

    def fail_network(self, node):
        data = self.snapshots[node]["data"]
        data["network"]["google"] = False
        data["network"]["cloudflare"] = False
        data["cloudflare_edge"]["reachable"] = 0

    def test_healthy(self):
        self.assertEqual(self.diagnose(), "none")

    def test_shared_wan(self):
        for node in NODES:
            self.fail_network(node)
        self.assertEqual(
            self.diagnose(),
            "possible_shared_wan_issue",
        )

    def test_shared_edge(self):
        for node in NODES:
            self.snapshots[node]["data"][
                "cloudflare_edge"
            ]["reachable"] = 0

        self.assertEqual(
            self.diagnose(),
            "possible_shared_edge_issue",
        )

    def test_primary_failure(self):
        self.fail_network(NODES[0])
        self.assertEqual(
            self.diagnose(),
            "possible_primary_host_issue",
        )

    def test_secondary_failure(self):
        self.fail_network(NODES[1])
        self.assertEqual(
            self.diagnose(),
            "possible_secondary_host_issue",
        )

    def test_offline_agent(self):
        self.availability[NODES[0]] = "offline"
        self.assertEqual(
            self.diagnose(), "agent_unavailable"
        )

    def test_stale_snapshot(self):
        self.snapshots[NODES[0]]["timestamp"] = 900
        self.assertEqual(
            self.diagnose(), "stale_snapshot"
        )

    def test_snapshot_skew(self):
        self.snapshots[NODES[0]]["timestamp"] = 980
        self.assertEqual(
            self.diagnose(), "snapshots_not_aligned"
        )

    def test_tunnel_offline(self):
        self.snapshots[NODES[0]]["data"]["tunnel"] = {
            "connections": 0,
            "health": "offline",
        }
        self.assertEqual(
            self.diagnose(), "tunnel_specific_issue"
        )

    def test_tunnel_degraded(self):
        self.snapshots[NODES[0]]["data"]["tunnel"] = {
            "connections": 1,
            "health": "degraded",
        }
        self.assertEqual(
            self.diagnose(),
            "tunnel_redundancy_reduced",
        )

    def test_website_failure(self):
        self.snapshots[NODES[0]]["data"]["website"] = {
            "online": False,
            "http_code": 502,
        }

        self.assertEqual(
            self.diagnose(), "website_specific_issue"
        )

    def test_missing_network_data(self):
        del self.snapshots[NODES[0]]["data"]["network"]
        self.assertEqual(
            self.diagnose(), "network_data_missing"
        )


if __name__ == "__main__":
    unittest.main()
