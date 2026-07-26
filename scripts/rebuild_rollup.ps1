<#
.SYNOPSIS
  Rebuild pu_results + ward/LGA/state roll-ups from evidence, in a VISIBLE terminal,
  excluding low-confidence polling units from the totals.

.DESCRIPTION
  Loads DATABASE_URL from backend/.env, then runs
    python -m scripts.pick_definitive_results --build-results --min-confidence <N>
  Each pu_results row is (re)scored for confidence; only units at or above the
  threshold are summed into ward/LGA/state totals. This is a large write over the
  remote DB, so it runs in its own visible PowerShell window with live progress.

.PARAMETER MinConfidence
  Minimum confidence (0-100) a PU must have to count in the roll-up. Default 80.

.PARAMETER Commit
  Actually write. Without it, a dry run that writes nothing.

.PARAMETER NoNewWindow
  Run inline instead of spawning a visible window (for CI).

.EXAMPLE
  ./rebuild_rollup.ps1 -Commit               # min-confidence 80, visible window
  ./rebuild_rollup.ps1 -MinConfidence 80 -Commit
#>
[CmdletBinding()]
param(
    [int]$MinConfidence = 80,
    [switch]$Commit,
    [switch]$NoNewWindow
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Split-Path -Parent $ScriptDir
$EnvFile = Join-Path $BackendDir '.env'

if (-not $env:DATABASE_URL) {
    if (-not (Test-Path $EnvFile)) { throw "DATABASE_URL not set and no .env at $EnvFile" }
    foreach ($line in Get-Content $EnvFile) {
        $t = $line.Trim()
        if ($t -and -not $t.StartsWith('#') -and $t.Contains('=')) {
            $k, $v = $t.Split('=', 2)
            if ($k.Trim() -eq 'DATABASE_URL') { $env:DATABASE_URL = $v.Trim().Trim('"').Trim("'") }
        }
    }
}
if (-not $env:DATABASE_URL) { throw "DATABASE_URL is empty after reading $EnvFile" }

$commitArg = if ($Commit) { '--commit' } else { '' }
$mode = if ($Commit) { "COMMIT (writing, min-confidence $MinConfidence)" } else { "DRY RUN" }

$inner = @"
Set-Location '$BackendDir'
`$env:DATABASE_URL = '$($env:DATABASE_URL)'
Write-Host '=== rebuild roll-up  |  $mode ===' -ForegroundColor Cyan
python -m scripts.pick_definitive_results --build-results --min-confidence $MinConfidence $commitArg
Write-Host ''
Write-Host 'Done. Press any key to close this window.' -ForegroundColor Green
`$null = `$Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
"@

if ($NoNewWindow) {
    Write-Host "=== rebuild roll-up  |  $mode ===" -ForegroundColor Cyan
    Push-Location $BackendDir
    try { python -m scripts.pick_definitive_results --build-results --min-confidence $MinConfidence $commitArg }
    finally { Pop-Location }
} else {
    Write-Host "Launching a visible terminal for the roll-up rebuild ($mode)..." -ForegroundColor Yellow
    Start-Process -FilePath 'powershell.exe' `
        -ArgumentList '-NoExit', '-NoProfile', '-Command', $inner
    Write-Host "A new window opened running the rebuild. Watch it there." -ForegroundColor Yellow
}
