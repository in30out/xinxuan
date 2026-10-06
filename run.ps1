# run.ps1 -- start the "XinXuan" web UI + JSON API.
# Usage (from anywhere):  powershell -ExecutionPolicy Bypass -File run.ps1
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 parses .ps1 as ANSI unless the
#       file carries a UTF-8 BOM; keeping the script body ASCII removes that whole failure
#       mode. (The Flask app's own Chinese output is UTF-8 and works fine.)

$ErrorActionPreference = "Continue"

# repo root = this script's directory
$ws = $PSScriptRoot
if (-not $ws) { $ws = Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $ws

# 1) pick an interpreter: verified DSH runtime first, then whatever `python` is on PATH
$py = "C:\Users\13718\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $py)) {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) { $py = $cmd.Source }
}
if (-not $py) {
  Write-Host "[X] Python not found. Install Python 3.10+, or edit the path at the top of run.ps1."
  exit 1
}

# 2) dependencies: prefer .venv (path A), else the .deps bundle (path B)
$venvPy  = Join-Path $ws ".venv\Scripts\python.exe"
$depsDir = Join-Path $ws ".deps"
if (Test-Path $venvPy) {
  $py = $venvPy
} elseif (Test-Path $depsDir) {
  $env:PYTHONPATH = $depsDir
} else {
  Write-Host "[!] Neither .venv nor .deps found; dependencies are probably not installed."
  Write-Host "    Path A: python -m venv .venv; .venv\Scripts\python -m pip install -r requirements.txt"
  Write-Host "    Path B: python scripts\fetch_deps.py --target .deps"
}

# 3) UTF-8 console (Chinese output from the app)
chcp 65001 > $null
$env:PYTHONIOENCODING = "utf-8"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

# 4) dataset + port
if (-not $env:CHIPS_CSV) {
  $csv = Join-Path $ws "data\samples\chips_seed.csv"
  if (Test-Path $csv) { $env:CHIPS_CSV = $csv }
}
if (-not $env:PORT) { $env:PORT = "5000" }

Write-Host ""
Write-Host "XinXuan - chip alternative selection recommender"
Write-Host ("  python : " + $py)
Write-Host ("  deps   : " + $(if ($env:PYTHONPATH) { $env:PYTHONPATH } else { "venv / system" }))
Write-Host ("  data   : " + $env:CHIPS_CSV)
Write-Host ("  url    : http://127.0.0.1:" + $env:PORT)
Write-Host "  Ctrl+C to stop"
Write-Host ""

& $py (Join-Path $ws "prototype\app.py")
