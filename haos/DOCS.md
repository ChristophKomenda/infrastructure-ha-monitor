# Configuration

Install two external Linux monitoring agents from the upstream repository. Configure distinct node IDs and use them here. Stop the old correlation engine before starting this app: only one correlation engine per MQTT namespace is supported.

Use a dedicated MQTT account with access to the two agent snapshot and availability topics and write access to correlation and discovery topics. TLS is enabled by default with public CA verification. Custom CA and client certificates are not exposed in this initial package. Disable TLS only on a trusted isolated network if required.

SQLite data persists under /data/history. Existing external history is not automatically migrated. Back up before switching. Hardware, Docker and network probes stay on the external agents. Missing observations do not prove downtime; diagnoses do not prove root cause.

HAOS runtime and live MQTT validation are pending.
