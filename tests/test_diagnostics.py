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

from diagnostics import classify, tunnel_health


class TunnelHealthTests(unittest.TestCase):

    def test_healthy(self):
        self.assertEqual(tunnel_health(4), "healthy")

    def test_degraded(self):
        self.assertEqual(tunnel_health(1), "degraded")

    def test_offline(self):
        self.assertEqual(tunnel_health(0), "offline")

    def test_unavailable(self):
        self.assertEqual(
            tunnel_health(None), "unavailable"
        )


class IncidentTests(unittest.TestCase):

    def setUp(self):
        self.network = {
            "gateway": True,
            "google": True,
            "cloudflare": True,
        }
        self.tunnels = {"primary": "healthy"}
        self.websites = {"example": True}
        self.edges = {"reachable": 4, "total": 4}
        self.dns = {"online": True}

    def classify(self):
        return classify(
            self.network,
            self.tunnels,
            self.websites,
            self.edges,
            self.dns,
        )

    def test_healthy(self):
        self.assertEqual(
            self.classify(), ("healthy", "none")
        )

    def test_gateway_failure(self):
        self.network["gateway"] = False
        self.assertEqual(
            self.classify(),
            ("critical", "gateway_probe_failed")
        )

    def test_tunnel_offline(self):
        self.tunnels["primary"] = "offline"
        self.assertEqual(
            self.classify(),
            ("critical", "tunnel_offline")
        )

    def test_tunnel_degraded(self):
        self.tunnels["primary"] = "degraded"
        self.assertEqual(
            self.classify(),
            ("degraded", "tunnel_redundancy_reduced")
        )

    def test_partial_edge_failure(self):
        self.edges["reachable"] = 1
        self.assertEqual(
            self.classify(),
            ("degraded", "partial_edge_reachability")
        )

    def test_edge_failure(self):
        self.edges["reachable"] = 0
        self.assertEqual(
            self.classify(),
            ("critical", "cloudflare_edge_unreachable")
        )

    def test_website_failure(self):
        self.websites["example"] = False
        self.assertEqual(
            self.classify(),
            ("critical", "website_unreachable")
        )

    def test_missing_metrics(self):
        self.tunnels["primary"] = "unavailable"
        self.assertEqual(
            self.classify(),
            ("unknown", "tunnel_metrics_unavailable")
        )


if __name__ == "__main__":
    unittest.main()
