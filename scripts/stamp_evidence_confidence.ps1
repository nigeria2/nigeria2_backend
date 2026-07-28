<#
.SYNOPSIS
  Stamp qwen LLM evidence rows with a 0-100 confidence score, in a VISIBLE terminal.

.DESCRIPTION
  Loads DATABASE_URL from backend/.env, then runs
  scripts/stamp_evidence_confidence.py, which scores each qwen transcription from the
  quality of its result sheet (missing/blurry/inflated = low, clean = high). Dry-run by
  default; -Commit writes. Launched in its own visible PowerShell window with live output.

.PARAMETER Commit
  Actually write. Without it, a dry run that only prints the distribution.

.PARAMETER NoNewWindow
  Run inline in the current terminal instead of spawning a visible window (for CI).

.EXAMPLE
  ./stamp_evidence_confidence.ps1            # dry run in a visible window
  ./stamp_evidence_confidence.ps1 -Commit    # apply, in a visible window
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

# '' would be passed to python as a literal empty arg and argparse rejects it
$commitArg = if ($Commit) { '--commit' } else { $null }
$mode = if ($Commit) { 'COMMIT (writing)' } else { 'DRY RUN (no writes)' }

$inner = @"
Set-Location '$BackendDir'
`$env:DATABASE_URL = '$($env:DATABASE_URL)'
Write-Host '=== stamp qwen evidence confidence  |  $mode ===' -ForegroundColor Cyan
python -m scripts.stamp_evidence_confidence $commitArg
if (`$LASTEXITCODE -ne 0) { Write-Host "exited with code `$LASTEXITCODE" -ForegroundColor Red }
Write-Host ''
Write-Host 'Done. Press any key to close this window.' -ForegroundColor Green
`$null = `$Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
"@

if ($NoNewWindow) {
    Write-Host "=== stamp qwen evidence confidence  |  $mode ===" -ForegroundColor Cyan
    Push-Location $BackendDir
    try { python -m scripts.stamp_evidence_confidence $commitArg } finally { Pop-Location }
} else {
    Write-Host "Launching a visible terminal for the evidence-confidence stamp ($mode)..." -ForegroundColor Yellow
    Start-Process -FilePath 'powershell.exe' `
        -ArgumentList '-NoExit', '-NoProfile', '-Command', $inner
    Write-Host "A new window opened running the stamp. Watch it there." -ForegroundColor Yellow
}
