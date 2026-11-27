"""Bounded dynamic Cloudflare TCP endpoint monitoring."""

import ipaddress
import time

from diagnostics import discover_edges, edge_monitor


class DynamicEdges:

    def __init__(self, limit=8, refresh=300):
        self.limit = max(1, min(int(limit), 20))
        self.refresh = max(60, int(refresh))
        self.addresses = []
        self.updated = None

    def targets(self):
        now = time.monotonic()

        if (
            self.updated is None
            or now - self.updated >= self.refresh
        ):
            addresses = []

            for value in discover_edges():
                try:
                    address = ipaddress.IPv4Address(value)
                    if address.is_global:
                        addresses.append(address)
                except ValueError:
                    continue

            if addresses:
                self.addresses = [
                    str(address)
                    for address in sorted(set(addresses))
                ][:self.limit]

            self.updated = now

        return list(self.addresses)

    def collect(self):
        targets = self.targets()

        if not targets:
            return {
                "reachable": None,
                "total": 0,
            }

        result = edge_monitor(targets)

        return {
            "reachable": result["reachable"],
            "total": result["total"],
        }
