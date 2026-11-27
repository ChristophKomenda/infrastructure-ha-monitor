"""MQTT service for cross-host infrastructure correlation."""

import json
import logging
import signal
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from correlation import NODES as DEFAULT_NODES, correlate
import math
import re
from confirmation import Confirmation
from mqtt_security import configure_tls
from storage import History
from boot_tracker import BootTracker


ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "config.json").read_text())

NODES = tuple(CONFIG.get(
    "correlation_nodes", DEFAULT_NODES
))

if (
    len(NODES) != 2
    or len(set(NODES)) != 2
    or not all(
        isinstance(node, str)
        and re.fullmatch(r"[a-zA-Z0-9_-]+", node)
        for node in NODES
    )
):
    raise ValueError("Invalid correlation_nodes")

HISTORY = History(ROOT / "data" / "infrastructure.sqlite3")
BOOTS = BootTracker(HISTORY.db)
TRACKER = Confirmation(confirmations=2)
STATS_CACHE = {}
LAST_STATS = 0
LAST_CLEANUP = 0

BASE = "infrastructure_monitor/correlation"
AVAILABILITY = f"{BASE}/availability"

STOP = threading.Event()
LOCK = threading.Lock()

snapshots = {}
availability = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

log = logging.getLogger("infrastructure-correlation")

client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id="infrastructure_monitor_correlation",
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


SENSORS = {
    "primary_reboot_count": ("Primary Reboot Count", None),
    "secondary_reboot_count": ("Secondary Reboot Count", None),
    "status": ("Status", None),
    "raw_status": ("Raw Status", None),
    "raw_diagnosis": ("Raw Diagnosis", None),
    "incident_count": ("Incident Count", None),
    "completed_incidents": ("Completed Incidents", None),
    "mttr": ("MTTR", "s"),
    "mtbf": ("MTBF", "s"),
    "last_incident_duration": ("Last Incident Duration", "s"),
    "active_incident_duration": ("Active Incident Duration", "s"),
    "uptime_24h": ("Uptime 24h", "%"),
    "uptime_7d": ("Uptime 7d", "%"),
    "uptime_30d": ("Uptime 30d", "%"),
    "coverage_24h": ("Coverage 24h", "%"),
    "coverage_7d": ("Coverage 7d", "%"),
    "coverage_30d": ("Coverage 30d", "%"),
    "healthy_24h": ("Healthy 24h", "%"),
    "healthy_7d": ("Healthy 7d", "%"),
    "healthy_30d": ("Healthy 30d", "%"),
    "diagnosis": ("Diagnosis", None),
    "detail": ("Detail", None),
    "agents_online": ("Agents Online", None),
    "primary_status": ("Primary Status", None),
    "secondary_status": ("Secondary Status", None),
    "snapshot_skew": ("Snapshot Difference", "s"),
    "snapshot_age_max": ("Maximum Snapshot Age", "s"),
}


def register_entities():
    for key, (name, unit) in SENSORS.items():
        uid = f"infra_correlation_{key}"

        payload = {
            "name": name,
            "unique_id": uid,
            "state_topic": f"{BASE}/snapshot",
            "value_template": (
                "{{ value_json." + key + " }}"
            ),
            "availability_topic": AVAILABILITY,
            "expire_after": 45,
            "device": {
                "identifiers": [
                    "infrastructure_correlation"
                ],
                "name": "Infrastructure Correlation",
                "manufacturer": "Infrastructure HA Monitor",
                "sw_version": "1.0.0",
            },
        }

        if unit:
            payload["unit_of_measurement"] = unit

        client.publish(
            f"homeassistant/sensor/{uid}/config",
            json.dumps(payload),
            qos=1,
            retain=True,
        )


def on_connect(client, userdata, flags, reason, properties):
    if reason != 0:
        log.error("MQTT rejected: %s", reason)
        return

    with LOCK:
        snapshots.clear()
        availability.clear()

    for node in NODES:
        client.subscribe(
            f"infrastructure_monitor/{node}/snapshot",
            qos=1,
        )
        client.subscribe(
            f"infrastructure_monitor/{node}/availability",
            qos=1,
        )

    register_entities()
    client.publish(
        AVAILABILITY, "online", qos=1, retain=True
    )

    log.info("Correlation engine connected")


def on_message(client, userdata, message):
    try:
        _, node, kind = message.topic.split("/")
        if node not in NODES:
            return

        payload = message.payload.decode()

        with LOCK:
            if kind == "availability":
                availability[node] = payload

            elif kind == "snapshot":
                data = json.loads(payload)

                if isinstance(data, dict):
                    snapshots[node] = data

    except (ValueError, UnicodeError):
        log.warning("Invalid MQTT payload")


client.on_connect = on_connect
client.on_message = on_message


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

last_result = None

try:
    while not STOP.is_set():

        if not client.is_connected():
            STOP.wait(5)
            continue

        with LOCK:
            current = snapshots.copy()
            available = availability.copy()

        try:
            now = time.time()

            result = correlate(
                current, available, now=now,
                nodes=NODES
            )

            for node in NODES:
                if available.get(node) == "online":
                    BOOTS.observe_snapshot(
                        node, current.get(node), now
                    )

            result["primary_reboot_count"] = BOOTS.count(
                NODES[0]
            )
            result["secondary_reboot_count"] = BOOTS.count(
                NODES[1]
            )

            raw_status = result["status"]
            raw_diagnosis = result["diagnosis"]

            pair = tuple(
                float(current[node]["timestamp"])
                for node in NODES
            ) if raw_status != "unknown" else ()

            status, diagnosis = TRACKER.update(
                raw_status, raw_diagnosis, pair
            )

            result["raw_status"] = raw_status
            result["raw_diagnosis"] = raw_diagnosis
            result["status"] = status
            result["diagnosis"] = diagnosis

            history_status = (
                "pending"
                if diagnosis == "confirmation_pending"
                else status
            )

            HISTORY.record(
                history_status, diagnosis, now
            )

            if now - LAST_STATS >= 60 or not STATS_CACHE:
                STATS_CACHE = HISTORY.statistics(now)

                for label, hours in (
                    ("24h", 24),
                    ("7d", 168),
                    ("30d", 720),
                ):
                    metrics = HISTORY.availability(hours, now)

                    for key, value in metrics.items():
                        STATS_CACHE[f"{key}_{label}"] = value

                LAST_STATS = now

            result.update(STATS_CACHE)
            result.update(HISTORY.live_statistics(now))

            if now - LAST_CLEANUP >= 3600:
                HISTORY.cleanup(now=now)
                LAST_CLEANUP = now

            result["agents_online"] = sum(
                available.get(node) == "online"
                for node in NODES
            )

            result["primary_status"] = current.get(
                NODES[0], {}
            ).get("status", "unknown")

            result["secondary_status"] = current.get(
                NODES[1], {}
            ).get("status", "unknown")

            timestamps = []

            for node in NODES:
                try:
                    timestamp = float(
                        current[node]["timestamp"]
                    )
                    if math.isfinite(timestamp):
                        timestamps.append(timestamp)
                except (KeyError, TypeError, ValueError):
                    pass

            result["snapshot_age_max"] = (
                round(max(now - t for t in timestamps), 2)
                if timestamps else None
            )

            result["snapshot_skew"] = (
                round(abs(timestamps[0] - timestamps[1]), 2)
                if len(timestamps) == 2 else None
            )

            client.publish(
                f"{BASE}/snapshot",
                json.dumps(result, allow_nan=False),
                qos=1,
                retain=True,
            )

            diagnosis = (
                result["status"],
                result["diagnosis"],
                result["detail"],
            )

            if diagnosis != last_result:
                log.info(
                    "Correlation status=%s diagnosis=%s detail=%s",
                    *diagnosis,
                )
                last_result = diagnosis

        except Exception:
            log.exception("Correlation cycle failed")

        STOP.wait(5)

finally:
    if client.is_connected():
        client.publish(
            AVAILABILITY,
            "offline",
            qos=1,
            retain=True,
        ).wait_for_publish(timeout=3)

    client.disconnect()
    client.loop_stop()
    HISTORY.close()
