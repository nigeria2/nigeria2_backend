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
  ./rebuild_rollup.ps1 -Commit               # uses the default floor, visible window
  ./rebuild_rollup.ps1 -MinConfidence 80 -Commit
#>
[CmdletBinding()]
param(
    # 0 = use app/confidence.MIN_ROLLUP_CONFIDENCE (the single source of truth).
    # Don't hard-code a number here: the ladder was rescaled once and a stale 80 in this
    # script silently cut the two "unsure" tiers out of the national totals.
    [int]$MinConfidence = 0,
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

# NOTE: build the arg list as an ARRAY. Interpolating an empty string for the non-commit
# case passes a literal '' through to python, which argparse rejects with
# "unrecognized arguments" — that made the spawned window die instantly.
$pyArgs = @('-u', '-m', 'scripts.pick_definitive_results', '--build-results')
if ($MinConfidence -gt 0) { $pyArgs += @('--min-confidence', "$MinConfidence") }
if ($Commit) { $pyArgs += '--commit' }
$argLine = ($pyArgs -join ' ')
$mode = if ($Commit) { "COMMIT (writing, min-confidence $MinConfidence)" } else { "DRY RUN" }

# try/catch + pause on BOTH paths so a crash stays readable instead of closing the window
$inner = @"
Set-Location '$BackendDir'
`$env:DATABASE_URL = '$($env:DATABASE_URL)'
Write-Host '=== rebuild roll-up  |  $mode ===' -ForegroundColor Cyan
try { python $argLine } catch { Write-Host "ERROR: `$_" -ForegroundColor Red }
if (`$LASTEXITCODE -ne 0) { Write-Host "exited with code `$LASTEXITCODE" -ForegroundColor Red }
Write-Host ''
Write-Host 'Done. Press any key to close this window.' -ForegroundColor Green
`$null = `$Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
"@

if ($NoNewWindow) {
    Write-Host "=== rebuild roll-up  |  $mode ===" -ForegroundColor Cyan
    Push-Location $BackendDir
    try { python @pyArgs } finally { Pop-Location }
} else {
    Write-Host "Launching a visible terminal for the roll-up rebuild ($mode)..." -ForegroundColor Yellow
    Start-Process -FilePath 'powershell.exe' `
        -ArgumentList '-NoExit', '-NoProfile', '-Command', $inner
    Write-Host "A new window opened running the rebuild. Watch it there." -ForegroundColor Yellow
}
