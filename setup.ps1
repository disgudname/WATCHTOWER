#Requires -RunAsAdministrator
<#
.SYNOPSIS
    WATCHTOWER one-time setup. Clone, fill in .env, run this once.
.DESCRIPTION
    1. Verifies Python 3.9+
    2. Creates a virtual environment
    3. Installs Python dependencies
    4. Copies config.example.env → .env (if not already present)
    5. Initialises the SQLite database
    6. Registers a Task Scheduler task that starts WATCHTOWER at boot
#>

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

function Write-Step($msg) { Write-Host "`n  $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  !!  $msg" -ForegroundColor Yellow }

Write-Host ""
Write-Host "  ══════════════════════════════════════" -ForegroundColor DarkGray
Write-Host "   WATCHTOWER  ·  setup" -ForegroundColor White
Write-Host "  ══════════════════════════════════════" -ForegroundColor DarkGray

# ── 1. Python ─────────────────────────────────────────────────────────────────
Write-Step "Checking Python..."
$pyCmd = $null
foreach ($candidate in @("python", "python3")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -lt 9) {
                Write-Error "Python 3.9+ required (found $ver). Please upgrade."
            }
            $pyCmd = $candidate
            Write-Ok "$ver"
            break
        }
    } catch { }
}
if (-not $pyCmd) {
    Write-Error "Python not found in PATH. Install Python 3.9+ from python.org and retry."
}

# ── 2. Virtual environment ────────────────────────────────────────────────────
Write-Step "Setting up virtual environment..."
$venvDir = Join-Path $Root "venv"
if (-not (Test-Path $venvDir)) {
    & $pyCmd -m venv $venvDir
    Write-Ok "Created venv at $venvDir"
} else {
    Write-Ok "venv already exists"
}

$pip    = Join-Path $venvDir "Scripts\pip.exe"
$python = Join-Path $venvDir "Scripts\python.exe"

# ── 3. Dependencies ───────────────────────────────────────────────────────────
Write-Step "Installing Python dependencies..."
& $pip install --quiet --upgrade pip
& $pip install --quiet -r (Join-Path $Root "requirements.txt")
Write-Ok "Dependencies installed"

# ── 4. .env file ──────────────────────────────────────────────────────────────
Write-Step "Checking .env config..."
$envFile     = Join-Path $Root ".env"
$envExample  = Join-Path $Root "config.example.env"
if (-not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
    Write-Host ""
    Write-Host "  ┌────────────────────────────────────────────────────────┐" -ForegroundColor Yellow
    Write-Host "  │  ACTION REQUIRED: edit .env before starting WATCHTOWER │" -ForegroundColor Yellow
    Write-Host "  │  Fill in: TRACCAR_PASS, OPENWEATHERMAP_API_KEY         │" -ForegroundColor Yellow
    Write-Host "  │  File: $envFile" -ForegroundColor Yellow
    Write-Host "  └────────────────────────────────────────────────────────┘" -ForegroundColor Yellow
} else {
    Write-Ok ".env already present"
}

# ── 5. Database ───────────────────────────────────────────────────────────────
Write-Step "Initialising database..."
$initScript = @"
import sqlite3, os
db = os.path.join(r'$Root', 'route.db')
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
"@
& $python -c $initScript
Write-Ok "Database initialised"

# ── 6. Task Scheduler ─────────────────────────────────────────────────────────
Write-Step "Registering Task Scheduler task..."
$taskName = "WATCHTOWER"

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Warn "Task '$taskName' already exists — skipping registration."
    Write-Warn "To re-register: Unregister-ScheduledTask -TaskName WATCHTOWER -Confirm:`$false, then re-run setup.ps1"
} else {
    $pythonAbs = (Resolve-Path $python).Path
    $appAbs    = (Resolve-Path (Join-Path $Root "app.py")).Path

    $action = New-ScheduledTaskAction `
        -Execute    $pythonAbs `
        -Argument   "`"$appAbs`"" `
        -WorkingDirectory $Root

    $trigger = New-ScheduledTaskTrigger -AtStartup

    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit  (New-TimeSpan -Hours 0) `
        -RestartCount        10 `
        -RestartInterval     (New-TimeSpan -Minutes 1) `
        -StartWhenAvailable  `
        -MultipleInstances   IgnoreNew

    $principal = New-ScheduledTaskPrincipal `
        -UserId    "SYSTEM" `
        -RunLevel  Highest

    Register-ScheduledTask `
        -TaskName   $taskName `
        -Action     $action `
        -Trigger    $trigger `
        -Settings   $settings `
        -Principal  $principal `
        -Description "WATCHTOWER overlay relay — 2026 Reset Trip"

    Write-Ok "Task '$taskName' registered (runs as SYSTEM at boot)"
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ══════════════════════════════════════" -ForegroundColor DarkGray
Write-Host "   Setup complete." -ForegroundColor White
Write-Host ""
Write-Host "   Next steps:" -ForegroundColor White
Write-Host "     1. Edit .env with your credentials (if you haven't yet)" -ForegroundColor Gray
Write-Host "     2. Run .\start.ps1 to launch WATCHTOWER now" -ForegroundColor Gray
Write-Host "     3. Open OBS browser sources:" -ForegroundColor Gray
Write-Host "          http://localhost:5000/live  (LIVE overlay)" -ForegroundColor DarkCyan
Write-Host "          http://localhost:5000/dark  (OFF-GRID card)" -ForegroundColor DarkCyan
Write-Host "   The task auto-starts on every reboot." -ForegroundColor Gray
Write-Host "  ══════════════════════════════════════" -ForegroundColor DarkGray
Write-Host ""
