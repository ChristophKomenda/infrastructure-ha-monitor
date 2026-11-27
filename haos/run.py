import json
import os
import re
import sys
from pathlib import Path


def build_config(options):
    nodes = [options['primary_node'], options['secondary_node']]
    if len(set(nodes)) != 2 or not all(re.fullmatch(r'[a-zA-Z0-9_-]+', n) for n in nodes):
        raise ValueError('Configure two distinct node IDs')
    if not all(options[k] for k in ('mqtt_host', 'mqtt_username', 'mqtt_password')):
        raise ValueError('Configure dedicated MQTT credentials and host')
    if type(options['mqtt_tls']) is not bool:
        raise ValueError('mqtt_tls must be boolean')
    if type(options['mqtt_port']) is not int or not 1 <= options['mqtt_port'] <= 65535:
        raise ValueError('Invalid MQTT port')
    return {'correlation_nodes': nodes, 'mqtt': {
        k: options['mqtt_' + k] for k in ('host', 'port', 'username', 'password', 'tls')}}


def main():
    os.umask(0o077)
    data = Path('/data')
    config = build_config(json.loads((data / 'options.json').read_text()))
    (data / 'history').mkdir(exist_ok=True)
    temporary = data / 'config.json.tmp'
    temporary.write_text(json.dumps(config))
    temporary.chmod(0o600)
    temporary.replace(data / 'config.json')
    os.execv(sys.executable, [sys.executable, '/app/src/infrastructure_ha_monitor/correlation_service.py'])


if __name__ == '__main__':
    main()
