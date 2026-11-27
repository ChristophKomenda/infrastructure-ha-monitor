# Infrastructure HA Monitor — Docker, Cloudflare and Server Monitoring for Home Assistant

Distributed infrastructure monitoring and cross-host
incident correlation for Home Assistant.

A lightweight Python monitoring system for Linux servers,
Raspberry Pi, Docker, Cloudflare Tunnel and self-hosted
infrastructure, using native MQTT Discovery.

## Features

- Distributed monitoring agents
- Configurable two-host incident correlation
- HTTP availability and response times
- Verified public HTTPS certificate monitoring
- Cloudflare Tunnel connections and redundancy
- Static and dynamic Cloudflare TCP endpoint probes
- DNS resolution monitoring
- ICMP latency and packet loss
- Linux network and conntrack diagnostics
- Raspberry Pi power and temperature diagnostics
- Host uptime and boot identification
- Persistent observed reboot counters
- Filesystem capacity and mount availability
- Docker restart and OOM diagnostics
- Persistent SQLite incident history
- MTTR, MTBF, uptime and measurement coverage
- MQTT authentication and optional verified TLS
- Home Assistant MQTT Discovery
- systemd installation and service management

## Architecture

    Primary monitoring agent ------+
                                    |
                                    v
                               MQTT Broker
                                    |
    Secondary monitoring agent ----+
                                    |
                                    v
                            Correlation Engine
                                    |
                           SQLite Incident History
                                    |
                                    v
                              Home Assistant

Agents collect measurements independently.
The correlation engine compares fresh snapshots
from two configured hosts and classifies symptoms
without claiming a proven root cause.

## Home Assistant OS app

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FChristophKomenda%2Fhome-assistant-apps)

Install **Infrastructure HA Monitor** from the [Community Apps repository](https://github.com/ChristophKomenda/home-assistant-apps). The experimental app runs the correlation engine only; two external Linux agents remain required. Do not run two correlation engines against the same broker namespace. See [app setup](haos/DOCS.md). HAOS runtime validation is pending.

## Requirements

- Linux with systemd
- Python 3.11 or newer
- Python venv and pip
- curl, ping and getent
- MQTT broker
- Home Assistant with MQTT integration
- Docker access for optional container monitoring
- vcgencmd for optional Raspberry Pi diagnostics

## Installation

Clone the repository:

    git clone https://github.com/ChristophKomenda/infrastructure-ha-monitor.git
    cd infrastructure-ha-monitor

Create the local configuration:

    cp config.example.json config.json
    chmod 600 config.json
    nano config.json

Install a monitoring agent:

    bash scripts/manage.sh install agent

Install the correlation service on one host:

    bash scripts/manage.sh install correlation

To install both services on one host:

    bash scripts/manage.sh install both

Configure distinct node IDs on the two monitored hosts.
Set correlation_nodes to those same two IDs in the
correlation host configuration.

## Home Assistant

Enable the MQTT integration in Home Assistant.

Entities are automatically registered through MQTT Discovery.
No custom Home Assistant component or dashboard is required.

## Security

Use a dedicated MQTT account and restrictive broker ACLs.
Do not expose an unauthenticated MQTT broker to the internet.

For TLS, configure mqtt.tls, the broker hostname and
the appropriate port. Optionally configure mqtt.tls_ca_file,
mqtt.tls_cert_file and mqtt.tls_key_file.

Certificate validation must remain enabled.

Docker access is highly privileged. Only grant it to a
trusted monitoring account when container checks are needed.

Never commit config.json, credentials or runtime databases.

## Updates

Back up configuration and runtime data first.

Fetch a trusted release and check out its version.
Then run:

    bash scripts/manage.sh update agent

Use correlation or both where appropriate.
The update command installs the checked-out source;
it does not automatically fetch new releases.

## Uninstallation

    bash scripts/manage.sh uninstall both

Configuration and SQLite history are preserved.
Retained MQTT Discovery entries must be removed separately
if the associated Home Assistant entities are no longer needed.

## Observability

Uptime measures the percentage of observed time
classified as healthy or degraded.

Coverage indicates how much of the requested time window
was actually observed.

MTTR is calculated from confirmed, recovered incidents.
MTBF is estimated from observed intervals between incidents.

Missing measurements are not proof of downtime.

Reboot counts track observed boot-ID changes after installation.
They do not reconstruct historical or unobserved reboots.

Dynamic Cloudflare endpoint checks and extended hardware
measurements provide supplemental diagnostic evidence.

## Limitations

- Correlation currently supports exactly two configured hosts.
- Only one correlation engine per MQTT namespace is supported.
- Public HTTPS checks inspect the served certificate,
  not a private origin certificate behind Cloudflare.
- Diagnosis is rule-based and does not prove root cause.
- Hardware checks depend on operating system support
  and available permissions.

## Tests

    python -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python -m unittest discover -s tests -v

## License

MIT

<!-- github-seo:begin -->

## Related projects

- [Pironman 5 Home Assistant Integration](https://github.com/ChristophKomenda/pironman5-homeassistant-container)
- [Powerline2MQTT — dLAN monitoring](https://github.com/ChristophKomenda/powerline2mqtt)
- [Bitcoin Pi Node — Raspberry Pi deployment](https://github.com/ChristophKomenda/bitcoin-pi-node)

## Frequently asked questions — quick answers

### How can I monitor Cloudflare Tunnel and Docker in Home Assistant?

This project collects infrastructure measurements on Linux hosts and publishes them using MQTT discovery. Consult the configuration and installation instructions for supported checks.

### What is cross-host incident correlation?

Monitoring agents collect independent measurements. The correlation engine compares fresh snapshots from configured hosts to help classify symptoms. It does not guarantee identification of the root cause.

<!-- github-seo:end -->
