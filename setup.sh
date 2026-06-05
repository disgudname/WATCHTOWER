#!/usr/bin/env bash
# WATCHTOWER one-time setup. Clone, fill in .env, run this once (no sudo needed).
# 1. Verifies Python 3.9+
# 2. Creates a virtual environment
# 3. Installs Python dependencies
# 4. Copies config.example.env → .env (if not already present)
# 5. Initialises the SQLite database
# 6. Registers a systemd user service that starts WATCHTOWER at boot

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

step()  { printf '\n  \033[36m%s\033[0m\n' "$*"; }
ok()    { printf '  \033[32mOK\033[0m  %s\n' "$*"; }
warn()  { printf '  \033[33m!!\033[0m  %s\n' "$*"; }

printf '\n'
printf '  \033[90m══════════════════════════════════════\033[0m\n'
printf '   WATCHTOWER  ·  setup\n'
printf '  \033[90m══════════════════════════════════════\033[0m\n'

# ── 1. Python ──────────────────────────────────────────────────────────────────
step "Checking Python..."
PY_CMD=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" --version 2>&1)
        if [[ $ver =~ Python\ 3\.([0-9]+) ]]; then
            minor="${BASH_REMATCH[1]}"
            if (( minor < 9 )); then
                echo "  Python 3.9+ required (found $ver). Please upgrade." >&2
                exit 1
            fi
            PY_CMD="$candidate"
            ok "$ver"
            break
        fi
    fi
done
if [[ -z "$PY_CMD" ]]; then
    echo "  Python not found in PATH. Install Python 3.9+ and retry." >&2
    exit 1
fi

# ── 2. Virtual environment ─────────────────────────────────────────────────────
step "Setting up virtual environment..."
VENV_DIR="$ROOT/venv"
if [[ ! -d "$VENV_DIR" ]]; then
    "$PY_CMD" -m venv "$VENV_DIR"
    ok "Created venv at $VENV_DIR"
else
    ok "venv already exists"
fi

PIP="$VENV_DIR/bin/pip"
PYTHON="$VENV_DIR/bin/python"

# ── 3. Dependencies ────────────────────────────────────────────────────────────
step "Installing Python dependencies..."
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -r "$ROOT/requirements.txt"
ok "Dependencies installed"

# ── 4. .env file ───────────────────────────────────────────────────────────────
step "Checking .env config..."
ENV_FILE="$ROOT/.env"
ENV_EXAMPLE="$ROOT/config.example.env"
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    printf '\n'
    printf '  \033[33m┌────────────────────────────────────────────────────────┐\033[0m\n'
    printf '  \033[33m│  ACTION REQUIRED: edit .env before starting WATCHTOWER │\033[0m\n'
    printf '  \033[33m│  Fill in: TRACCAR_PASS, OPENWEATHERMAP_API_KEY         │\033[0m\n'
    printf '  \033[33m│  File: %s\033[0m\n' "$ENV_FILE"
    printf '  \033[33m└────────────────────────────────────────────────────────┘\033[0m\n'
else
    ok ".env already present"
fi

# ── 5. Database ────────────────────────────────────────────────────────────────
step "Initialising database..."
"$PYTHON" - <<PYEOF
import sqlite3, os
db = os.path.join('$ROOT', 'route.db')
conn = sqlite3.connect(db)
conn.execute('''
    CREATE TABLE IF NOT EXISTS positions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   TEXT    NOT NULL,
        lat         REAL    NOT NULL,
        lon         REAL    NOT NULL,
        speed_mph   REAL,
        heading_deg REAL,
        city_state  TEXT
    )
''')
conn.commit()
conn.close()
print('route.db ready')
PYEOF
ok "Database initialised"

# ── 6. systemd user service ────────────────────────────────────────────────────
step "Registering systemd user service..."
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/watchtower.service"
mkdir -p "$SERVICE_DIR"

if [[ -f "$SERVICE_FILE" ]]; then
    warn "Service 'watchtower' already exists — skipping registration."
    warn "To re-register: rm $SERVICE_FILE, then re-run setup.sh"
else
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=WATCHTOWER overlay relay — 2026 Reset Trip
After=network.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$PYTHON $ROOT/app.py
Restart=on-failure
RestartSec=5s
EnvironmentFile=$ROOT/.env

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable watchtower.service
    # Enable lingering so the service starts at boot without a login session
    if command -v loginctl &>/dev/null; then
        loginctl enable-linger "$(whoami)" 2>/dev/null || true
    fi
    ok "Service 'watchtower' registered (starts at boot)"
fi

# ── Done ───────────────────────────────────────────────────────────────────────
printf '\n'
printf '  \033[90m══════════════════════════════════════\033[0m\n'
printf '   Setup complete.\n\n'
printf '   Next steps:\n'
printf '     1. Edit .env with your credentials (if you have not yet)\n'
printf '     2. Run ./start.sh to launch WATCHTOWER now\n'
printf '     3. Open OBS browser sources:\n'
printf '          \033[36mhttp://localhost:5000/live\033[0m  (LIVE overlay)\n'
printf '          \033[36mhttp://localhost:5000/dark\033[0m  (OFF-GRID card)\n'
printf '   The service auto-starts on every reboot.\n'
printf '  \033[90m══════════════════════════════════════\033[0m\n\n'
