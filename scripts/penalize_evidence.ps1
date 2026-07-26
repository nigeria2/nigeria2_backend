<#
.SYNOPSIS
  Penalize evidence confidence for minor-party OCR misreads, in a VISIBLE terminal.

.DESCRIPTION
  Loads DATABASE_URL from backend/.env, then runs scripts/penalize_evidence.py: for
  2023 presidential evidence, any minor party (not LP/APC/PDP/NNPP) recorded with > 2000
  votes gets -50 confidence, and the deduction is recorded in evidence_penalties.
  Dry-run by default; -Commit writes. Runs in its own visible PowerShell window.

.PARAMETER Commit
  Actually write. Without it, a dry run that prints what it would do.

.PARAMETER NoNewWindow
  Run inline instead of spawning a visible window (for CI).

.EXAMPLE
  ./penalize_evidence.ps1            # dry run in a visible window
  ./penalize_evidence.ps1 -Commit    # apply, in a visible window
#>
[CmdletBinding()]
param(
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
Write-Host '=== penalize minor-party OCR misreads  |  $mode ===' -ForegroundColor Cyan
python -m scripts.penalize_evidence $commitArg
Write-Host ''
Write-Host 'Done. Press any key to close this window.' -ForegroundColor Green
`$null = `$Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
"@

if ($NoNewWindow) {
    Write-Host "=== penalize minor-party OCR misreads  |  $mode ===" -ForegroundColor Cyan
    Push-Location $BackendDir
    try { python -m scripts.penalize_evidence $commitArg } finally { Pop-Location }
} else {
    Write-Host "Launching a visible terminal for the penalty pass ($mode)..." -ForegroundColor Yellow
    Start-Process -FilePath 'powershell.exe' `
        -ArgumentList '-NoExit', '-NoProfile', '-Command', $inner
    Write-Host "A new window opened running the penalty pass. Watch it there." -ForegroundColor Yellow
}
