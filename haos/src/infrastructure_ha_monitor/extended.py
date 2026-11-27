"""Extended Linux infrastructure diagnostics."""

import json
import re
import shutil
import socket
import ssl
import subprocess
import time

from pathlib import Path
from urllib.parse import urlsplit


def read_text(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def command(args, timeout=5):
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def parse_throttled(value):
    try:
        flags = int(value.split("=")[-1], 16)
    except (AttributeError, ValueError):
        return {}

    return {
        "undervoltage": bool(flags & 1),
        "frequency_capped": bool(flags & 2),
        "throttled": bool(flags & 4),
        "temperature_limit": bool(flags & 8),
        "historical_undervoltage": bool(flags & (1 << 16)),
        "historical_throttled": bool(flags & (1 << 18)),
    }


def host_metrics():
    result = {
        "boot_id": read_text(
            "/proc/sys/kernel/random/boot_id"
        )
    }

    try:
        uptime = float(
            read_text("/proc/uptime").split()[0]
        )
        result["uptime_seconds"] = round(uptime, 1)
    except (AttributeError, ValueError, IndexError):
        result["uptime_seconds"] = None

    try:
        result["cpu_temperature"] = round(
            float(read_text(
                "/sys/class/thermal/thermal_zone0/temp"
            )) / 1000, 1
        )
    except (TypeError, ValueError):
        result["cpu_temperature"] = None

    result.update(parse_throttled(command(
        ["vcgencmd", "get_throttled"]
    )))

    return result


def filesystem_metrics(path):
    path = Path(path)

    if not path.is_mount():
        return {
            "mounted": False,
            "usage": None,
            "free_gib": None,
        }

    try:
        usage = shutil.disk_usage(path)

        return {
            "mounted": True,
            "usage": round(
                usage.used / usage.total * 100, 2
            ),
            "free_gib": round(
                usage.free / 1024**3, 2
            ),
        }
    except OSError:
        return {
            "mounted": None,
            "usage": None,
            "free_gib": None,
        }


def docker_metrics(name):
    try:
        result = subprocess.run(
            [
                "docker", "inspect",
                "--format", "{{json .}}", name,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )

        data = json.loads(result.stdout)
        state = data["State"]

        return {
            "running": state["Running"],
            "oom_killed": state["OOMKilled"],
            "restart_count": data["RestartCount"],
            "started_at": state["StartedAt"],
        }
    except (
        OSError, ValueError, KeyError,
        subprocess.SubprocessError,
    ):
        return {
            "running": None,
            "oom_killed": None,
            "restart_count": None,
            "started_at": None,
        }


def tls_certificate(url):
    result = {
        "valid": None,
        "days_remaining": None,
        "expires_at": None,
    }

    parsed = urlsplit(url)

    if parsed.scheme != "https" or not parsed.hostname:
        return result

    try:
        context = ssl.create_default_context()

        with socket.create_connection(
            (parsed.hostname, parsed.port or 443),
            timeout=5,
        ) as connection:
            with context.wrap_socket(
                connection,
                server_hostname=parsed.hostname,
            ) as secure:
                certificate = secure.getpeercert()

        expires = certificate["notAfter"]
        remaining = ssl.cert_time_to_seconds(
            expires
        ) - time.time()

        result.update({
            "valid": True,
            "days_remaining": round(
                remaining / 86400, 2
            ),
            "expires_at": expires,
        })

    except ssl.SSLCertVerificationError:
        result["valid"] = False
    except (OSError, ValueError, KeyError):
        pass

    return result


def icmp_metrics(host):
    output = command(
        ["ping", "-n", "-c", "3", "-W", "1", host],
        timeout=6,
    )

    result = {
        "packet_loss": None,
        "latency": None,
    }

    if not output:
        return result

    loss = re.search(
        r"([\d.]+)% packet loss", output
    )

    if loss:
        result["packet_loss"] = float(loss.group(1))

    latency = re.search(
        r"=\s*[\d.]+/([\d.]+)/[\d.]+/[\d.]+",
        output,
    )

    if latency:
        result["latency"] = float(latency.group(1))

    return result


def tcp_latency(host, port=7844):
    start = time.monotonic()

    try:
        with socket.create_connection(
            (host, port), timeout=3
        ):
            return round(
                (time.monotonic() - start) * 1000, 2
            )
    except OSError:
        return None
