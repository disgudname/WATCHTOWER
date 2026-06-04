<#
.SYNOPSIS
    Start or restart WATCHTOWER. Safe to run at any time — idempotent.
    Use this from AnyDesk if the service needs a kick.
#>

$ErrorActionPreference = "SilentlyContinue"
$taskName = "WATCHTOWER"

Write-Host ""
Write-Host "  WATCHTOWER  ·  start / restart" -ForegroundColor Cyan
Write-Host ""

# Check setup has been run
$task = Get-ScheduledTask -TaskName $taskName
if (-not $task) {
    Write-Host "  Task '$taskName' not found." -ForegroundColor Red
    Write-Host "  Run setup.ps1 first (as Administrator)." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# Check .env exists
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "  .env not found — copy config.example.env to .env and fill in credentials." -ForegroundColor Red
    Write-Host ""
    exit 1
}

# Stop if already running
$state = ($task | Get-ScheduledTaskInfo).LastTaskResult
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Start
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 2

$info = Get-ScheduledTaskInfo -TaskName $taskName
$running = (Get-ScheduledTask -TaskName $taskName).State

Write-Host "  Status : $running" -ForegroundColor $(if ($running -eq 'Running') {'Green'} else {'Yellow'})
Write-Host ""
Write-Host "  Overlays (once running):" -ForegroundColor White
Write-Host "    http://localhost:5000/live" -ForegroundColor DarkCyan
Write-Host "    http://localhost:5000/dark" -ForegroundColor DarkCyan
Write-Host "    http://localhost:5000/api/status" -ForegroundColor DarkGray
Write-Host ""
