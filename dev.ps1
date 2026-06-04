<#
.SYNOPSIS
    Run WATCHTOWER in dev mode — no admin, no Task Scheduler.
    Sets up the venv on first run, then starts the app directly.
    Ctrl+C to stop.
#>

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

# ── Virtual environment ───────────────────────────────────────────────────────
$venvDir = Join-Path $Root "venv"
if (-not (Test-Path $venvDir)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv $venvDir
}

$pip    = Join-Path $venvDir "Scripts\pip.exe"
$python = Join-Path $venvDir "Scripts\python.exe"

# ── Dependencies ──────────────────────────────────────────────────────────────
Write-Host "Checking dependencies..." -ForegroundColor Cyan
& $pip install --quiet -r (Join-Path $Root "requirements.txt")

# ── .env ─────────────────────────────────────────────────────────────────────
$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $Root "config.example.env") $envFile
    Write-Host ""
    Write-Host "  Created .env from template." -ForegroundColor Yellow
    Write-Host "  Edit it before continuing - set TRACCAR_URL, TRACCAR_PASS, OPENWEATHERMAP_API_KEY." -ForegroundColor Yellow
    Write-Host "  File: $envFile" -ForegroundColor Gray
    Write-Host ""
    Read-Host "  Press Enter when .env is ready"
}

# ── Run ───────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Starting WATCHTOWER (dev mode)..." -ForegroundColor Cyan
Write-Host "  http://localhost:5000/live" -ForegroundColor DarkCyan
Write-Host "  http://localhost:5000/dark" -ForegroundColor DarkCyan
Write-Host "  Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

& $python (Join-Path $Root "app.py")
