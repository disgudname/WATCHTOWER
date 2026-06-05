#!/usr/bin/env bash
# Run WATCHTOWER in dev mode — no systemd, just run it directly.
# Sets up the venv on first run, then starts the app.
# Ctrl+C to stop.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Virtual environment ────────────────────────────────────────────────────────
VENV_DIR="$ROOT/venv"
if [[ ! -d "$VENV_DIR" ]]; then
    printf '\033[36mCreating virtual environment...\033[0m\n'
    python3 -m venv "$VENV_DIR"
fi

PIP="$VENV_DIR/bin/pip"
PYTHON="$VENV_DIR/bin/python"

# ── Dependencies ───────────────────────────────────────────────────────────────
printf '\033[36mChecking dependencies...\033[0m\n'
"$PIP" install --quiet -r "$ROOT/requirements.txt"

# ── .env ──────────────────────────────────────────────────────────────────────
ENV_FILE="$ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$ROOT/config.example.env" "$ENV_FILE"
    printf '\n  \033[33mCreated .env from template.\033[0m\n'
    printf '  \033[33mEdit it before continuing — set TRACCAR_URL, TRACCAR_PASS, OPENWEATHERMAP_API_KEY.\033[0m\n'
    printf '  \033[90mFile: %s\033[0m\n\n' "$ENV_FILE"
    read -r -p "  Press Enter when .env is ready..."
fi

# ── Run ────────────────────────────────────────────────────────────────────────
printf '\n  \033[36mStarting WATCHTOWER (dev mode)...\033[0m\n'
printf '  \033[36mhttp://localhost:5000/live\033[0m\n'
printf '  \033[36mhttp://localhost:5000/dark\033[0m\n'
printf '  \033[90mCtrl+C to stop.\033[0m\n\n'

exec "$PYTHON" "$ROOT/app.py"
