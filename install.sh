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
PYTHON_BIN=python3
while (($#)); do
    case "$1" in
        --activate) ACTION=activate ;;
        --backend=*) BACKEND="${1#--backend=}" ;;
        --backend) shift; BACKEND="${1:-}" ;;
        --service-status) ACTION=status ;;
        --remove-cron) ACTION=remove-cron ;;
        --python=*) PYTHON_BIN="${1#--python=}" ;;
        --python)
            shift
            if (($# == 0)); then
                printf 'Error: --python requires a Python executable.\n' >&2
                exit 2
            fi
            PYTHON_BIN="$1" ;;
        -h|--help)
            cat <<'USAGE'
Usage: ./install.sh [--python PATH] [--activate] [--backend=auto|systemd|cron|none]
       ./install.sh [--python PATH] --service-status
       ./install.sh [--python PATH] --remove-cron

Default: install/update the Python package and user config; do not start services.
--python: select the Python 3.11+ interpreter when creating a new .venv.
          An existing .venv is reused; it is never replaced automatically.
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

if [[ -z "$PYTHON_BIN" ]]; then
    printf 'Error: --python requires a non-empty executable path.\n' >&2
    exit 2
fi

if [[ "$ACTION" == status || "$ACTION" == remove-cron ]]; then
    STATUS_PYTHON="$PYTHON_BIN"
    if [[ "$PYTHON_BIN" == python3 && -x .venv/bin/python ]]; then
        STATUS_PYTHON=.venv/bin/python
    fi
    "$STATUS_PYTHON" deploy/service_manager.py --action "$ACTION"
    exit
fi

if [[ ! -x .venv/bin/python ]]; then
    if ! "$PYTHON_BIN" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
        printf 'Error: Python 3.11+ is required. Use --python /path/to/python.\n' >&2
        exit 2
    fi
    "$PYTHON_BIN" -m venv .venv
fi

if ! .venv/bin/python -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    printf 'Error: Existing .venv uses an unsupported Python version.\n' >&2
    printf 'Preserve or move the old .venv before creating a new one with --python.\n' >&2
    exit 2
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
