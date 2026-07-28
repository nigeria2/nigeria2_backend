<#
.SYNOPSIS
  Load the 2023 crosschecked/unsure transcriptions as PU evidence, in a VISIBLE terminal.

.DESCRIPTION
  Loads DATABASE_URL from backend/.env, then runs
  scripts/load_2023_transcriptions.py, which reads data/2023_data/*_crosschecked.csv
  (confidence 90) and *_unsure.csv (confidence 70) and loads each polling unit's 2023
  presidential result as kind='2023_transcription' evidence. Dry-run by default;
  -Commit writes. Launched in its own visible PowerShell window with live output.

.PARAMETER Commit
  Actually write. Without it, a dry run that prints what it would load.

.PARAMETER NoNewWindow
  Run inline in the current terminal instead of spawning a visible window (for CI).

.EXAMPLE
  ./load_2023_transcriptions.ps1            # dry run in a visible window
  ./load_2023_transcriptions.ps1 -Commit    # write, in a visible window
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
Write-Host '=== load 2023 transcriptions as evidence  |  $mode ===' -ForegroundColor Cyan
python -m scripts.load_2023_transcriptions $commitArg
if (`$LASTEXITCODE -ne 0) { Write-Host "exited with code `$LASTEXITCODE" -ForegroundColor Red }
Write-Host ''
Write-Host 'Done. Press any key to close this window.' -ForegroundColor Green
`$null = `$Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
"@

if ($NoNewWindow) {
    Write-Host "=== load 2023 transcriptions as evidence  |  $mode ===" -ForegroundColor Cyan
    Push-Location $BackendDir
    try { python -m scripts.load_2023_transcriptions $commitArg } finally { Pop-Location }
} else {
    Write-Host "Launching a visible terminal for the 2023 transcription load ($mode)..." -ForegroundColor Yellow
    Start-Process -FilePath 'powershell.exe' `
        -ArgumentList '-NoExit', '-NoProfile', '-Command', $inner
    Write-Host "A new window opened running the load. Watch it there." -ForegroundColor Yellow
}
