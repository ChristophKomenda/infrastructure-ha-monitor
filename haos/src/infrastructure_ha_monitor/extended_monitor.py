"""Cached extended diagnostics for monitoring agents."""

import concurrent.futures
import time

from dynamic_edges import DynamicEdges

from extended import (
    host_metrics,
    filesystem_metrics,
    docker_metrics,
    tls_certificate,
    icmp_metrics,
)


class ExtendedMonitor:

    def __init__(self, config):
        self.config = config
        self.cache = {}
        self.dynamic_edges = DynamicEdges(
            limit=config.get("dynamic_edge_limit", 8)
        )


    def tasks(self):
        if self.config.get("dynamic_edges", True):
            yield (
                "Dynamic Cloudflare Edges",
                self.dynamic_edges.collect, (), 60,
                {
                    "reachable": None,
                    "total": None,
                },
            )


        yield (
            "Host Diagnostics",
            host_metrics, (), 30,
            {
                "boot_id": None,
                "uptime_seconds": "s",
                "cpu_temperature": "°C",
                "undervoltage": None,
                "frequency_capped": None,
                "throttled": None,
                "temperature_limit": None,
                "historical_undervoltage": None,
                "historical_throttled": None,
            },
        )

        for path in self.config.get("mounts", ["/"]):
            yield (
                f"Filesystem {path}",
                filesystem_metrics, (path,), 60,
                {
                    "mounted": None,
                    "usage": "%",
                    "free_gib": "GiB",
                },
            )

        for container in self.config.get("tunnels", []):
            yield (
                f"Docker {container}",
                docker_metrics, (container,), 30,
                {
                    "running": None,
                    "oom_killed": None,
                    "restart_count": None,
                    "started_at": None,
                },
            )

        for url in self.config.get("websites", []):
            if url.startswith("https://"):
                yield (
                    f"SSL {url[8:].rstrip('/')}",
                    tls_certificate, (url,), 300,
                    {
                        "valid": None,
                        "days_remaining": "d",
                        "expires_at": None,
                    },
                )

        targets = {
            "Gateway": self.config["gateway"],
            "Cloudflare": "1.1.1.1",
            "Google": "8.8.8.8",
        }

        for name, host in targets.items():
            yield (
                f"ICMP {name}",
                icmp_metrics, (host,), 30,
                {
                    "packet_loss": "%",
                    "latency": "ms",
                },
            )

    def register(self, discovery):
        for device, _, _, _, fields in self.tasks():
            for key, unit in fields.items():
                discovery(
                    device,
                    key,
                    key.replace("_", " ").title(),
                    unit=unit,
                )

    def collect(self, state):
        now = time.monotonic()

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=8
        ) as pool:
            jobs = {}

            for device, fn, args, interval, fields in self.tasks():
                previous = self.cache.get(device)

                if (
                    previous is None
                    or now - previous[0] >= interval
                ):
                    jobs[pool.submit(fn, *args)] = (
                        device, fields
                    )

            for future in concurrent.futures.as_completed(jobs):
                device, fields = jobs[future]

                try:
                    values = future.result()
                except Exception:
                    values = {}

                self.cache[device] = (
                    time.monotonic(),
                    {
                        key: values.get(key)
                        for key in fields
                    },
                )

        for device, (_, values) in self.cache.items():
            for key, value in values.items():
                state(device, key, value)
