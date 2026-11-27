"""Cross-host infrastructure incident correlation."""

import time
import math


NODES = ("webserver_pi", "homeassistant_pi")


def correlate(
    snapshots,
    availability,
    now=None,
    max_age=35,
    max_skew=15,
    nodes=NODES,
):
    now = time.time() if now is None else now

    def result(status, diagnosis, detail):
        return {
            "status": status,
            "diagnosis": diagnosis,
            "detail": detail,
        }

    if (
        len(nodes) != 2
        or nodes[0] == nodes[1]
    ):
        return result(
            "unknown", "invalid_configuration",
            "Two distinct node IDs required",
        )

    for node in nodes:
        if availability.get(node) != "online":
            return result(
                "unknown", "agent_unavailable", node
            )

        snapshot = snapshots.get(node)

        if not isinstance(snapshot, dict):
            return result(
                "unknown", "snapshot_missing", node
            )

        if (
            snapshot.get("schema_version") != 1
            or snapshot.get("node_id") != node
        ):
            return result(
                "unknown", "invalid_snapshot", node
            )

        try:
            age = now - float(snapshot["timestamp"])
        except (KeyError, TypeError, ValueError):
            return result(
                "unknown", "invalid_timestamp", node
            )

        if not math.isfinite(age):
            return result(
                "unknown", "invalid_timestamp", node
            )

        if age < -5 or age > max_age:
            return result(
                "unknown", "stale_snapshot", node
            )

    primary, secondary = (
        snapshots[node] for node in nodes
    )

    skew = abs(
        float(primary["timestamp"])
        - float(secondary["timestamp"])
    )

    if skew > max_skew:
        return result(
            "unknown",
            "snapshots_not_aligned",
            f"Timestamp difference: {skew:.1f}s",
        )

    p = primary.get("data", {})
    s = secondary.get("data", {})

    if not isinstance(p, dict) or not isinstance(s, dict):
        return result(
            "unknown", "invalid_snapshot_data",
            "Snapshot data must be an object",
        )

    pn = p.get("network", {})
    sn = s.get("network", {})

    pe = p.get("cloudflare_edge", {})
    se = s.get("cloudflare_edge", {})

    for network in (pn, sn):
        if not isinstance(network, dict):
            return result(
                "unknown", "network_data_missing",
                "Invalid network measurements",
            )
        if any(
            type(network.get(key)) is not bool
            for key in ("gateway", "google", "cloudflare")
        ):
            return result(
                "unknown",
                "network_data_missing",
                "Incomplete network measurements",
            )

    for edges in (pe, se):
        if not isinstance(edges, dict):
            return result(
                "unknown", "edge_data_missing",
                "Invalid edge measurements",
            )
        total = edges.get("total")
        reachable = edges.get("reachable")

        if (
            type(total) is not int
            or type(reachable) is not int
            or total <= 0
            or not 0 <= reachable <= total
        ):
            return result(
                "unknown",
                "edge_data_missing",
                "Incomplete edge measurements",
            )

    def internet_failed(network):
        return (
            network["google"] is False
            and network["cloudflare"] is False
        )

    def edge_failed(edges):
        return edges["reachable"] == 0

    def network_healthy(network, edges):
        return (
            all(
                network[key]
                for key in ("gateway", "google", "cloudflare")
            )
            and edges["reachable"] == edges["total"]
        )

    if not pn["gateway"] and not sn["gateway"]:
        return result(
            "critical",
            "possible_shared_gateway_issue",
            "Gateway probes failed on both hosts",
        )

    if (
        pn["gateway"]
        and sn["gateway"]
        and internet_failed(pn)
        and internet_failed(sn)
        and edge_failed(pe)
        and edge_failed(se)
    ):
        return result(
            "critical",
            "possible_shared_wan_issue",
            "External ICMP and TCP failed on both hosts",
        )

    if edge_failed(pe) and edge_failed(se):
        return result(
            "critical",
            "possible_shared_edge_issue",
            "Cloudflare TCP probes failed on both hosts",
        )

    if internet_failed(pn) and internet_failed(sn):
        return result(
            "degraded",
            "shared_icmp_probe_failure",
            "Both hosts failed external ICMP probes",
        )

    if (
        not network_healthy(pn, pe)
        and network_healthy(sn, se)
    ):
        return result(
            "degraded",
            "possible_primary_host_issue",
            "Only primary network probes are impaired",
        )

    if (
        not network_healthy(sn, se)
        and network_healthy(pn, pe)
    ):
        return result(
            "degraded",
            "possible_secondary_host_issue",
            "Only secondary network probes are impaired",
        )

    tunnels = {
        name: values.get("health")
        for name, values in p.items()
        if isinstance(values, dict)
        and "connections" in values
        and "health" in values
    }

    websites = {
        name: values.get("online")
        for name, values in p.items()
        if isinstance(values, dict)
        and "http_code" in values
    }

    offline = [
        name for name, health in tunnels.items()
        if health == "offline"
    ]

    if offline:
        return result(
            "critical",
            "tunnel_specific_issue",
            ", ".join(offline),
        )

    failed_sites = [
        name for name, online in websites.items()
        if online is False
    ]

    if failed_sites:
        return result(
            "critical",
            "website_specific_issue",
            ", ".join(failed_sites),
        )

    degraded = [
        name for name, health in tunnels.items()
        if health == "degraded"
    ]

    if degraded:
        return result(
            "degraded",
            "tunnel_redundancy_reduced",
            ", ".join(degraded),
        )

    if (
        p.get("infrastructure", {}).get(
            "raw_status", primary.get("status")
        ) == "healthy"
        and s.get("infrastructure", {}).get(
            "raw_status", secondary.get("status")
        ) == "healthy"
        and network_healthy(pn, pe)
        and network_healthy(sn, se)
    ):
        return result(
            "healthy", "none",
            "Both agents report healthy infrastructure",
        )

    return result(
        "unknown",
        "unclassified_or_pending",
        "Measurements require further confirmation",
    )
