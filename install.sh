#!/usr/bin/env bash
# Install HPC MCP and optionally activate a per-user Tunnel service.
# This script intentionally never uses sudo, su, or system-wide services.
set -euo pipefail

if [[ "$(id -u)" == 0 || "$(id -u)" != "$(id -ru)" ]]; then
    printf 'Error: run as the ordinary Linux user, never root.\n' >&2
    exit 1
fi

BACKEND=auto
ACTION=install
while (($#)); do
    case "$1" in
        --activate) ACTION=activate ;;
        --backend=*) BACKEND="${1#--backend=}" ;;
        --backend) shift; BACKEND="${1:-}" ;;
        --service-status) ACTION=status ;;
        --remove-cron) ACTION=remove-cron ;;
        -h|--help)
            cat <<'USAGE'
Usage: ./install.sh [--activate] [--backend=auto|systemd|cron|none]
       ./install.sh --service-status
       ./install.sh --remove-cron

Default: install/update the Python package and user config; do not start services.
--activate: set up per-user startup after private Tunnel credentials exist.
auto: persistent systemd --user if Linger=yes; otherwise usable user cron.
Neither root permissions nor any system-wide configuration is modified.
USAGE
            exit 0 ;;
        *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
    shift
done

case "$BACKEND" in
    auto|systemd|cron|none) ;;
    *) printf 'Invalid backend: %s\n' "$BACKEND" >&2; exit 2 ;;
esac

cd "$(dirname "$(readlink -f "$0")")"

if [[ "$ACTION" == status || "$ACTION" == remove-cron ]]; then
    python3 deploy/service_manager.py --action "$ACTION"
    exit
fi

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install -e .

install -d -m 700 "$HOME/.config/hpc-mcp"
if [[ ! -e "$HOME/.config/hpc-mcp/config.toml" ]]; then
    install -m 600 config/config.example.toml "$HOME/.config/hpc-mcp/config.toml"
fi
printf 'Installed hpc-mcp for %s at %s\n' "$USER" "$PWD"

if [[ "$ACTION" == activate ]]; then
    .venv/bin/python deploy/service_manager.py --action activate --backend "$BACKEND"
else
    printf 'Tunnel startup not changed. After setting private credentials, run:\n'
    printf '  ./install.sh --activate --backend=auto\n'
fi
