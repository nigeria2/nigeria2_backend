<#
.SYNOPSIS
  Apply evidence confidence PENALTY rules, in a VISIBLE terminal.

.DESCRIPTION
  Loads DATABASE_URL from backend/.env, then runs scripts/penalties.py. Each rule docks
  confidence from misread evidence and records why in evidence_penalties. Rules are
  idempotent and independent, so you can run one without disturbing another.
  Dry-run by default; -Commit writes. Runs in its own visible PowerShell window.

.PARAMETER Rules
  Comma-separated rule names, or 'all' (default). e.g. -Rules all_majors_zero_minors

.PARAMETER Commit
  Actually write. Without it, a dry run that prints what it would do.

.PARAMETER NoNewWindow
  Run inline instead of spawning a visible window (for CI).

.EXAMPLE
  ./penalties.ps1 -Rules all_majors_zero_minors -Commit   # apply just the new rule
  ./penalties.ps1 -Commit                                 # apply all rules
#>
[CmdletBinding()]
param(
    [string]$Rules = 'all',
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
$mode = if ($Commit) { 'COMMIT (writing)' } else { 'DRY RUN (no writes)' }

$inner = @"
Set-Location '$BackendDir'
`$env:DATABASE_URL = '$($env:DATABASE_URL)'
Write-Host '=== evidence penalties [$Rules]  |  $mode ===' -ForegroundColor Cyan
python -m scripts.penalties --rules $Rules $commitArg
Write-Host ''
Write-Host 'Done. Press any key to close this window.' -ForegroundColor Green
`$null = `$Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
"@

if ($NoNewWindow) {
    Write-Host "=== evidence penalties [$Rules]  |  $mode ===" -ForegroundColor Cyan
    Push-Location $BackendDir
    try { python -m scripts.penalties --rules $Rules $commitArg } finally { Pop-Location }
} else {
    Write-Host "Launching a visible terminal for the penalty rules [$Rules] ($mode)..." -ForegroundColor Yellow
    Start-Process -FilePath 'powershell.exe' `
        -ArgumentList '-NoExit', '-NoProfile', '-Command', $inner
    Write-Host "A new window opened running the penalty rules. Watch it there." -ForegroundColor Yellow
}
