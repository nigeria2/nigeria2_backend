<#
.SYNOPSIS
  Backfill pu_results.confidence (0-100) from sheet quality, in a VISIBLE terminal.

.DESCRIPTION
  Loads DATABASE_URL from backend/.env, then runs scripts/backfill_confidence.py.
  Missing-sheet-location and blurry/illegible results (and auto-voided inflated
  misreads) get a LOW score; clean sheets score high. Dry-run by default.

  This is a long-ish DB write over the remote Postgres, so it is launched in its own
  visible PowerShell window (Start-Process) whose output stays on screen until you
  press a key -- run this .ps1 directly and a new terminal appears with live progress.

.PARAMETER Commit
  Actually write. Without it, the run is a dry run that only prints the distribution.

.PARAMETER NoNewWindow
  Run inline in the current terminal instead of spawning a visible window (for CI).

.EXAMPLE
  ./backfill_confidence.ps1            # dry run in a visible window
  ./backfill_confidence.ps1 -Commit    # apply, in a visible window
#>
[CmdletBinding()]
param(
    [switch]$Commit,
    [switch]$NoNewWindow
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path   # backend/scripts
$BackendDir = Split-Path -Parent $ScriptDir                     # backend
$EnvFile = Join-Path $BackendDir '.env'

# --- load DATABASE_URL from backend/.env (KEY=VALUE per line) ---
if (-not $env:DATABASE_URL) {
    if (-not (Test-Path $EnvFile)) {
        throw "DATABASE_URL not set and no .env at $EnvFile"
    }
    foreach ($line in Get-Content $EnvFile) {
        $t = $line.Trim()
        if ($t -and -not $t.StartsWith('#') -and $t.Contains('=')) {
            $k, $v = $t.Split('=', 2)
            if ($k.Trim() -eq 'DATABASE_URL') {
                $env:DATABASE_URL = $v.Trim().Trim('"').Trim("'")
            }
        }
    }
}
if (-not $env:DATABASE_URL) { throw "DATABASE_URL is empty after reading $EnvFile" }

$commitArg = if ($Commit) { '--commit' } else { '' }
$mode = if ($Commit) { 'COMMIT (writing)' } else { 'DRY RUN (no writes)' }

# The command the visible window will run: cd into backend, run the module, then pause
# so the results stay readable after it finishes.
$inner = @"
Set-Location '$BackendDir'
`$env:DATABASE_URL = '$($env:DATABASE_URL)'
Write-Host '=== pu_results confidence backfill  |  $mode ===' -ForegroundColor Cyan
python -m scripts.backfill_confidence $commitArg
Write-Host ''
Write-Host 'Done. Press any key to close this window.' -ForegroundColor Green
`$null = `$Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
"@

if ($NoNewWindow) {
    Write-Host "=== pu_results confidence backfill  |  $mode ===" -ForegroundColor Cyan
    Push-Location $BackendDir
    try { python -m scripts.backfill_confidence $commitArg } finally { Pop-Location }
} else {
    Write-Host "Launching a visible terminal for the backfill ($mode)..." -ForegroundColor Yellow
    Start-Process -FilePath 'powershell.exe' `
        -ArgumentList '-NoExit', '-NoProfile', '-Command', $inner
    Write-Host "A new window opened running the backfill. Watch it there." -ForegroundColor Yellow
}
