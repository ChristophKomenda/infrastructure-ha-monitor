"""Infrastructure diagnostics and incident classification."""

import concurrent.futures
import socket
import subprocess
import time
from pathlib import Path


DEFAULT_EDGES = [
    "198.41.192.47",
    "198.41.200.73",
    "198.41.192.27",
    "198.41.200.33",
]


def tcp_probe(host, port=7844, timeout=3):
    started = time.monotonic()

    try:
        with socket.create_connection(
            (host, port), timeout=timeout
        ):
            return {
                "online": True,
                "latency": round(
                    (time.monotonic() - started) * 1000, 2
                ),
            }
    except OSError:
        return {
            "online": False,
            "latency": None,
        }


def edge_monitor(targets):
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=8
    ) as pool:
        results = list(pool.map(tcp_probe, targets))

    return {
        "reachable": sum(r["online"] for r in results),
        "total": len(targets),
        "results": dict(zip(targets, results)),
    }


def dns_probe(host):
    started = time.monotonic()

    try:
        result = subprocess.run(
            ["getent", "ahostsv4", host],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )

        return {
            "online": bool(result.stdout.strip()),
            "latency": round(
                (time.monotonic() - started) * 1000, 2
            ),
        }

    except (OSError, subprocess.SubprocessError):
        return {
            "online": False,
            "latency": None,
        }


def discover_edges():
    addresses = set()

    for hostname in (
        "region1.v2.argotunnel.com",
        "region2.v2.argotunnel.com",
    ):
        try:
            result = subprocess.run(
                ["getent", "ahostsv4", hostname],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            )

            for line in result.stdout.splitlines():
                parts = line.split()
                if parts:
                    addresses.add(parts[0])

        except (OSError, subprocess.SubprocessError):
            continue

    return sorted(addresses)


def read_number(path):
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def system_metrics(interface="eth0"):
    base = Path("/sys/class/net") / interface / "statistics"

    count = read_number(
        "/proc/sys/net/netfilter/nf_conntrack_count"
    )

    maximum = read_number(
        "/proc/sys/net/netfilter/nf_conntrack_max"
    )

    usage = None

    if count is not None and maximum:
        usage = round(count / maximum * 100, 4)

    return {
        "conntrack_count": count,
        "conntrack_max": maximum,
        "conntrack_usage": usage,
        "rx_errors": read_number(base / "rx_errors"),
        "tx_errors": read_number(base / "tx_errors"),
        "rx_dropped": read_number(base / "rx_dropped"),
        "tx_dropped": read_number(base / "tx_dropped"),
    }


def tunnel_health(connections, expected=4):
    if connections is None:
        return "unavailable"

    if connections <= 0:
        return "offline"

    if connections < expected:
        return "degraded"

    return "healthy"


def classify(network, tunnels, websites, edges, dns):
    """Classify symptoms without claiming a proven root cause."""

    if network.get("gateway") is False:
        return "critical", "gateway_probe_failed"

    if (
        network.get("google") is False
        and network.get("cloudflare") is False
    ):
        return "critical", "internet_probes_failed"

    if (
        edges.get("total", 0) > 0
        and edges.get("reachable") == 0
    ):
        return "critical", "cloudflare_edge_unreachable"

    if any(v == "offline" for v in tunnels.values()):
        return "critical", "tunnel_offline"

    if any(v is False for v in websites.values()):
        return "critical", "website_unreachable"

    if dns.get("online") is False:
        return "degraded", "dns_probe_failed"

    if any(v == "unavailable" for v in tunnels.values()):
        return "unknown", "tunnel_metrics_unavailable"

    if (
        edges.get("reachable", 0)
        < edges.get("total", 0)
    ):
        return "degraded", "partial_edge_reachability"

    if any(v == "degraded" for v in tunnels.values()):
        return "degraded", "tunnel_redundancy_reduced"

    if any(v is False for v in network.values()):
        return "degraded", "partial_network_reachability"

    return "healthy", "none"
