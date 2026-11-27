import sys
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

from extended import (
    parse_throttled,
    host_metrics,
    filesystem_metrics,
    icmp_metrics,
    tls_certificate,
)


class ExtendedTests(unittest.TestCase):

    def test_no_throttling(self):
        flags = parse_throttled("throttled=0x0")
        self.assertFalse(flags["undervoltage"])
        self.assertFalse(flags["throttled"])

    def test_undervoltage(self):
        flags = parse_throttled("throttled=0x10001")
        self.assertTrue(flags["undervoltage"])
        self.assertTrue(flags["historical_undervoltage"])

    def test_invalid_throttling(self):
        self.assertEqual(parse_throttled(None), {})

    def test_root_filesystem(self):
        result = filesystem_metrics("/")
        self.assertTrue(result["mounted"])

    def test_missing_mount(self):
        result = filesystem_metrics(
            "/nonexistent-infrastructure-test"
        )
        self.assertFalse(result["mounted"])

    @patch("extended.command")
    def test_icmp(self, command):
        command.return_value = (
            "3 packets transmitted, 2 received, "
            "33.3% packet loss\n"
            "rtt min/avg/max/mdev = "
            "10.0/15.0/20.0/2.0 ms"
        )

        result = icmp_metrics("example.invalid")

        self.assertEqual(result["packet_loss"], 33.3)
        self.assertEqual(result["latency"], 15)

    def test_non_https(self):
        result = tls_certificate(
            "http://example.invalid"
        )
        self.assertIsNone(result["valid"])

    def test_host_metrics(self):
        self.assertIn("boot_id", host_metrics())


if __name__ == "__main__":
    unittest.main()
