# Perfection Verification Loop runner for Windows PowerShell.
#
# Usage:
#   .\scripts\perfection.ps1                  # full loop
#   .\scripts\perfection.ps1 -DryRun          # list gates and exit
#   .\scripts\perfection.ps1 -Phases "unit_backend,unit_frontend"
#   .\scripts\perfection.ps1 -ResetState      # start from cycle 0

param(
    [switch]$DryRun,
    [switch]$ResetState,
    [string]$Phases = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $RepoRoot "backend"

Push-Location $Backend
try {
    $cmd = @("python", "-m", "scripts.perfection_loop")
    if ($DryRun)     { $cmd += "--dry-run" }
    if ($ResetState) { $cmd += "--reset-state" }
    if ($Phases)     { $cmd += @("--phases", $Phases) }

    Write-Host "Running: $($cmd -join ' ')" -ForegroundColor Cyan
    & $cmd[0] $cmd[1..($cmd.Length - 1)]
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
