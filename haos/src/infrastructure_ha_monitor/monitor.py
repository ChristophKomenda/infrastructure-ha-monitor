import concurrent.futures
import json
import logging
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from incidents import IncidentTracker
from extended_monitor import ExtendedMonitor
from mqtt_security import configure_tls
from diagnostics import discover_edges

TRACKER = IncidentTracker(confirmations=2)
SNAPSHOT = {}


from diagnostics import (
    DEFAULT_EDGES,
    edge_monitor,
    dns_probe,
    system_metrics,
    tunnel_health,
    classify,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "config.json").read_text())

EXTENDED = ExtendedMonitor(CONFIG)

NODE = CONFIG["node_id"]
NODE_NAME = CONFIG.get("node_name", "")


def device_name(name):
    return f"{NODE_NAME} {name}" if NODE_NAME else name

BASE = f"infrastructure_monitor/{NODE}"
AVAILABILITY = f"{BASE}/availability"

STOP = threading.Event()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

log = logging.getLogger("infrastructure-monitor")


def slug(value):
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def command(args, timeout=8):
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    return result.stdout.strip()


def ping(host):
    try:
        command(["ping", "-c", "1", "-W", "2", host], 4)
        return True
    except Exception:
        return False


def website(url):
    try:
        output = command([
            "curl", "-L", "-sS",
            "--max-time", "8",
            "-o", "/dev/null",
            "-w", "%{http_code} %{time_total}",
            url,
        ], 10)

        code, elapsed = output.split()
        code = int(code)

        return {
            "online": 200 <= code < 400,
            "http_code": code,
            "response_time": round(float(elapsed) * 1000, 1),
        }

    except Exception:
        return {
            "online": False,
            "http_code": None,
            "response_time": None,
        }


def tunnel(container):
    template = (
        '{{(index .NetworkSettings.Networks "'
        + CONFIG["docker_network"]
        + '").IPAddress}}'
    )

    try:
        ip = command([
            "docker", "inspect",
            "--format", template, container,
        ])

        if not ip:
            return None

        output = command([
            "curl", "-fsS", "--max-time", "3",
            f"http://{ip}:20241/metrics",
        ])

        metrics = {}

        for line in output.splitlines():
            if line.startswith("#"):
                continue

            parts = line.split()

            if len(parts) >= 2:
                try:
                    metrics[parts[0]] = float(parts[1])
                except ValueError:
                    pass

        mapping = {
            "connections":
                "cloudflared_tunnel_ha_connections",
            "requests":
                "cloudflared_tunnel_total_requests",
            "errors":
                "cloudflared_tunnel_request_errors",
            "concurrent":
                "cloudflared_tunnel_concurrent_requests_per_tunnel",
        }

        return {
            key: metrics.get(metric)
            for key, metric in mapping.items()
        }

    except Exception as exc:
        log.warning("Tunnel %s: %s", container, exc)
        return None


client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=f"infrastructure_monitor_{NODE}",
)

client.username_pw_set(
    CONFIG["mqtt"]["username"],
    CONFIG["mqtt"]["password"],
)

client.will_set(
    AVAILABILITY,
    "offline",
    qos=1,
    retain=True,
)

configure_tls(client, CONFIG["mqtt"])

client.reconnect_delay_set(1, 60)


def publish(topic, payload, retain=True):
    if not client.is_connected():
        return None

    return client.publish(
        topic, payload, qos=1, retain=retain
    )


def discovery(
    device,
    key,
    name,
    component="sensor",
    unit=None,
    device_class=None,
):
    uid = f"infra_{NODE}_{slug(device)}_{key}"
    state = f"{BASE}/{slug(device)}/{key}"

    payload = {
        "name": name,
        "unique_id": uid,
        "state_topic": state,
        "availability_topic": AVAILABILITY,
        "expire_after": max(
            60, CONFIG["interval"] * 4
        ),
        "device": {
            "identifiers": [f"{NODE}_{slug(device)}"],
            "name": device_name(device),
            "manufacturer": "Infrastructure HA Monitor",
            "sw_version": "1.0.0",
        },
    }

    if unit:
        payload["unit_of_measurement"] = unit

    if device_class:
        payload["device_class"] = device_class

    if component == "binary_sensor":
        payload.pop("expire_after", None)
        payload["payload_on"] = "ON"
        payload["payload_off"] = "OFF"

    publish(
        f"homeassistant/{component}/{uid}/config",
        json.dumps(payload),
    )


def register_entities():
    EXTENDED.register(discovery)

    for name in CONFIG["tunnels"]:
        for key in [
            "connections", "requests",
            "errors", "concurrent"
        ]:
            discovery(
                name, key,
                key.replace("_", " ").title(),
            )

    for name in CONFIG["tunnels"]:
        discovery(name, "health", "Health")

    discovery("Infrastructure", "status", "Status")
    discovery("Infrastructure", "incident", "Incident")
    discovery("Infrastructure", "raw_status", "Raw Status")
    discovery("Infrastructure", "raw_incident", "Raw Incident")
    discovery("Infrastructure", "incident_count", "Incident Count")
    discovery(
        "Infrastructure", "incident_started_at",
        "Incident Started At"
    )

    for key in [
        "incident_duration",
        "last_incident_duration",
        "mttr",
    ]:
        discovery(
            "Infrastructure",
            key,
            key.replace("_", " ").title(),
            unit="s",
            device_class="duration",
        )

    discovery(
        "Cloudflare Edge",
        "discovered_endpoints",
        "Discovered Endpoints",
    )

    uid = f"infra_{NODE}_infrastructure_snapshot"

    publish(
        f"homeassistant/sensor/{uid}/config",
        json.dumps({
            "name": "Snapshot",
            "unique_id": uid,
            "state_topic": f"{BASE}/snapshot",
            "value_template": "{{ value_json.status }}",
            "json_attributes_topic": f"{BASE}/snapshot",
            "availability_topic": AVAILABILITY,
            "expire_after": max(
                60, CONFIG["interval"] * 4
            ),
            "device": {
                "identifiers": [
                    f"{NODE}_infrastructure"
                ],
                "name": device_name("Infrastructure"),
                "manufacturer": "Infrastructure HA Monitor",
                "sw_version": "1.0.0",
            },
        }),
    )

    discovery("Cloudflare Edge", "reachable", "Reachable")
    discovery("Cloudflare Edge", "total", "Total")

    for ip in CONFIG.get("edge_targets", DEFAULT_EDGES):
        discovery(
            "Cloudflare Edge",
            slug(ip) + "_online",
            ip + " Online",
            "binary_sensor",
            device_class="connectivity",
        )

        discovery(
            "Cloudflare Edge",
            slug(ip) + "_latency",
            ip + " TCP Latency",
            unit="ms",
            device_class="duration",
        )

    discovery(
        "DNS", "online", "Online",
        "binary_sensor",
        device_class="connectivity",
    )

    discovery(
        "DNS", "latency", "Resolution Time",
        unit="ms",
        device_class="duration",
    )

    for key in [
        "conntrack_count", "conntrack_max",
        "conntrack_usage", "rx_errors", "tx_errors",
        "rx_dropped", "tx_dropped"
    ]:
        discovery(
            "System Diagnostics",
            key,
            key.replace("_", " ").title(),
            unit="%" if key == "conntrack_usage" else None,
        )

    for url in CONFIG["websites"]:
        name = url.split("://", 1)[-1].rstrip("/")

        discovery(
            name, "online", "Online",
            "binary_sensor",
            device_class="connectivity",
        )

        discovery(name, "http_code", "HTTP Status")
        discovery(
            name, "response_time",
            "Response Time",
            unit="ms",
            device_class="duration",
        )

    for key in ["gateway", "cloudflare", "google"]:
        discovery(
            "Network", key, key.title(),
            "binary_sensor",
            device_class="connectivity",
        )


def state(device, key, value):
    SNAPSHOT.setdefault(slug(device), {})[key] = value
    if isinstance(value, bool):
        value = "ON" if value else "OFF"
    elif value is None:
        value = "None"

    publish(
        f"{BASE}/{slug(device)}/{key}",
        str(value),
    )


def on_connect(client, userdata, flags, reason, properties):
    if reason == 0:
        log.info("MQTT connected")
        register_entities()
        publish(AVAILABILITY, "online")
    else:
        log.error("MQTT connection rejected: %s", reason)


client.on_connect = on_connect


def run_cycle():
    SNAPSHOT.clear()
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=12
    ) as pool:

        jobs = {}

        network_results = {}
        tunnel_results = {}
        website_results = {}

        jobs[pool.submit(
            edge_monitor,
            CONFIG.get("edge_targets", DEFAULT_EDGES),
        )] = ("edges", "Cloudflare Edge")

        jobs[pool.submit(
            dns_probe,
            "region1.v2.argotunnel.com",
        )] = ("dns", "DNS")

        jobs[pool.submit(
            system_metrics,
            CONFIG.get("network_interface", "eth0"),
        )] = ("system", "System Diagnostics")

        jobs[pool.submit(discover_edges)] = (
            "edge_discovery", "Cloudflare Edge"
        )

        edges = {}
        dns = {}

        for name in CONFIG["tunnels"]:
            jobs[pool.submit(tunnel, name)] = (
                "tunnel", name
            )

        for url in CONFIG["websites"]:
            name = url.split("://", 1)[-1].rstrip("/")
            jobs[pool.submit(website, url)] = (
                "website", name
            )

        targets = {
            "gateway": CONFIG["gateway"],
            "cloudflare": "1.1.1.1",
            "google": "8.8.8.8",
        }

        for key, host in targets.items():
            jobs[pool.submit(ping, host)] = (
                "network", key
            )

        for future in concurrent.futures.as_completed(jobs):
            kind, name = jobs[future]
            result = future.result()

            if kind == "edge_discovery":
                state(name, "discovered_endpoints", len(result))
                SNAPSHOT.setdefault("cloudflare_edge", {})[
                    "discovered_addresses"
                ] = result
                continue

            if kind == "edges":
                edges = result

                log.info(
                    "Cloudflare TCP edges: %s/%s reachable",
                    result["reachable"],
                    result["total"],
                )

                state(name, "reachable", result["reachable"])
                state(name, "total", result["total"])

                for ip, values in result["results"].items():
                    state(
                        name, slug(ip) + "_online",
                        values["online"]
                    )
                    state(
                        name, slug(ip) + "_latency",
                        values["latency"]
                    )

                continue

            if kind == "dns":
                dns = result
                log.info("DNS probe: %s", result)
                for key, value in result.items():
                    state(name, key, value)
                continue

            if kind == "system":
                for key, value in result.items():
                    state(name, key, value)
                continue

            if kind == "tunnel":
                health = tunnel_health(
                    result.get("connections")
                    if result is not None else None
                )
                tunnel_results[name] = health
                state(name, "health", health)

            if kind == "website":
                website_results[name] = result["online"]

            if kind == "network":
                network_results[name] = result
                state("Network", name, result)

            elif result is None:
                for key in [
                    "connections", "requests",
                    "errors", "concurrent"
                ]:
                    state(name, key, None)

            else:
                for key, value in result.items():
                    state(name, key, value)

            log.info("%s %s: %s", kind, name, result)


        status, incident = classify(
            network_results,
            tunnel_results,
            website_results,
            edges,
            dns,
        )

        incident_data = TRACKER.update(status, incident)

        for key, value in incident_data.items():
            state("Infrastructure", key, value)

        EXTENDED.collect(state)

        publish(
            f"{BASE}/snapshot",
            json.dumps({
                "schema_version": 1,
                "node_id": NODE,
                "timestamp": time.time(),
                "status": incident_data["status"],
                "incident": incident_data["incident"],
                "data": SNAPSHOT,
            }),
        )

        log.info(
            "Infrastructure status=%s incident=%s raw=%s/%s",
            incident_data["status"],
            incident_data["incident"],
            status,
            incident,
        )


def stop(*args):
    STOP.set()


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

client.connect_async(
    CONFIG["mqtt"]["host"],
    CONFIG["mqtt"]["port"],
    keepalive=30,
)

client.loop_start()

try:
    while not STOP.is_set():
        started = time.monotonic()

        try:
            run_cycle()
        except Exception:
            log.exception("Monitoring cycle failed")

        STOP.wait(max(
            1,
            CONFIG["interval"]
            - (time.monotonic() - started)
        ))

finally:
    if client.is_connected():
        result = publish(AVAILABILITY, "offline")
        if result is not None:
            result.wait_for_publish(timeout=3)

    client.disconnect()
    client.loop_stop()
