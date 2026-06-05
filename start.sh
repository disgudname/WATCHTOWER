#!/usr/bin/env bash
# Start or restart WATCHTOWER. Safe to run at any time — idempotent.
# Use this from AnyDesk if the service needs a kick.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

printf '\n  \033[36mWATCHTOWER  ·  start / restart\033[0m\n\n'

# Check setup has been run
if ! systemctl --user cat watchtower.service &>/dev/null; then
    printf '  \033[31mService '\''watchtower'\'' not found.\033[0m\n'
    printf '  \033[33mRun setup.sh first.\033[0m\n\n'
    exit 1
fi

# Check .env exists
if [[ ! -f "$ROOT/.env" ]]; then
    printf '  \033[31m.env not found — copy config.example.env to .env and fill in credentials.\033[0m\n\n'
    exit 1
fi

# Restart (stop + start is idempotent)
systemctl --user restart watchtower.service

sleep 2

STATE=$(systemctl --user is-active watchtower.service 2>/dev/null || true)
if [[ "$STATE" == "active" ]]; then
    COLOR='\033[32m'
else
    COLOR='\033[33m'
fi

printf "  Status : ${COLOR}%s\033[0m\n\n" "$STATE"
printf '  Overlays (once running):\n'
printf '    \033[36mhttp://localhost:5000/live\033[0m\n'
printf '    \033[36mhttp://localhost:5000/dark\033[0m\n'
printf '    \033[90mhttp://localhost:5000/api/status\033[0m\n\n'
