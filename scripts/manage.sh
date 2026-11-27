#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ACTION="${1:-}"
ROLE="${2:-agent}"
USER_NAME="$(id -un)"

if [ "$(id -u)" -eq 0 ]; then
    echo "Run as a regular user with sudo access."
    exit 1
fi

if [[ "$ROOT" =~ [[:space:]] ]]; then
    echo "Installation path must not contain whitespace."
    exit 1
fi

if [[ "$ROLE" != agent && "$ROLE" != correlation && "$ROLE" != both ]]; then
    echo "Role must be agent, correlation or both."
    exit 1
fi

AGENT="infrastructure-ha-monitor"
CORRELATION="infrastructure-ha-correlation"

install_unit() {
    local service="$1"
    local module="$2"

    sudo tee "/etc/systemd/system/$service.service" \
        >/dev/null <<EOF
[Unit]
Description=$service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$ROOT
ExecStart=$ROOT/.venv/bin/python $ROOT/src/infrastructure_ha_monitor/$module
Restart=always
RestartSec=10
TimeoutStopSec=30
Environment=PYTHONUNBUFFERED=1
UMask=0077
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=full

[Install]
WantedBy=multi-user.target
EOF
    sudo chmod 644 \
        "/etc/systemd/system/$service.service"
}

case "$ACTION" in

    install|update)

        if [ ! -f config.json ]; then
            echo "Create config.json from config.example.json first."
            exit 1
        fi

        chmod 600 config.json

        if [ ! -d .venv ]; then
            python3 -m venv .venv
        fi

        .venv/bin/python -m pip install \
            -r requirements.txt

        .venv/bin/python -m compileall -q src

        .venv/bin/python -m unittest discover \
            -s tests -v

        if [[ "$ROLE" == agent || "$ROLE" == both ]]; then
            install_unit "$AGENT" monitor.py
        fi

        if [[ "$ROLE" == correlation || "$ROLE" == both ]]; then
            install_unit "$CORRELATION" correlation_service.py
        fi

        sudo systemctl daemon-reload

        if [[ "$ROLE" == agent || "$ROLE" == both ]]; then
            sudo systemctl enable "$AGENT.service"
            sudo systemctl restart "$AGENT.service"
        fi

        if [[ "$ROLE" == correlation || "$ROLE" == both ]]; then
            sudo systemctl enable "$CORRELATION.service"
            sudo systemctl restart "$CORRELATION.service"
        fi
        ;;

    uninstall)

        for service in "$AGENT" "$CORRELATION"
        do
            if [[ "$ROLE" == agent && "$service" != "$AGENT" ]]; then
                continue
            fi

            if [[ "$ROLE" == correlation && "$service" != "$CORRELATION" ]]; then
                continue
            fi

            sudo systemctl disable --now \
                "$service.service" 2>/dev/null || true

            sudo rm -f \
                "/etc/systemd/system/$service.service"
        done

        sudo systemctl daemon-reload

        echo "Services removed."
        echo "Configuration and history preserved."
        ;;

    *)
        echo "Usage:"
        echo "  $0 install agent|correlation|both"
        echo "  $0 update agent|correlation|both"
        echo "  $0 uninstall agent|correlation|both"
        exit 1
        ;;

esac
