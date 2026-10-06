# check.ps1 -- environment self-check for the "XinXuan" prototype.
# Usage (from anywhere):  powershell -ExecutionPolicy Bypass -File scripts\check.ps1
# NOTE: keep this file ASCII-only; Windows PowerShell 5.1 parses .ps1 as ANSI unless
#       the file has a UTF-8 BOM, and mixed encodings here caused real breakage before.

$ErrorActionPreference = "Continue"

# repo root = parent of this script's directory
$here = $PSScriptRoot
if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ws = Split-Path -Parent $here
Set-Location $ws

$script:fail = 0
function Ok($m)   { Write-Host ("[OK]   " + $m) }
function Bad($m)  { Write-Host ("[FAIL] " + $m); $script:fail++ }
function Warn($m) { Write-Host ("[WARN] " + $m) }

Write-Host "== XinXuan environment self-check =="
Write-Host ("   repo root: " + $ws)
Write-Host ""

# --- 1. interpreter -------------------------------------------------------
$py = "C:\Users\13718\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $py)) {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) { $py = $cmd.Source }
}
if (-not $py) { Bad "Python not found. Install Python 3.10+."; exit 1 }

$venvPy  = Join-Path $ws ".venv\Scripts\python.exe"
$depsDir = Join-Path $ws ".deps"
if (Test-Path $venvPy)      { $py = $venvPy;              Ok "using .venv virtualenv" }
elseif (Test-Path $depsDir) { $env:PYTHONPATH = $depsDir; Ok "using .deps bundle" }
else                        { Warn "neither .venv nor .deps found - imports below may fail" }
Ok ("Python: " + $py)

$env:PYTHONIOENCODING = "utf-8"

# --- 2. dependencies ------------------------------------------------------
$probe = Join-Path $ws "scripts\_check_deps.py"
if (Test-Path $probe) {
  $output = & $py $probe 2>&1
  $output | ForEach-Object { Write-Host ("       " + $_) }
  if ($LASTEXITCODE -eq 0) { Ok "dependencies present (numpy/pandas/sklearn/flask/jieba)" }
  else { Bad "missing dependencies -> python scripts\fetch_deps.py --target .deps" }
} else { Warn ("probe not found: " + $probe) }

# --- 3. dataset -----------------------------------------------------------
$csv = $env:CHIPS_CSV
if (-not $csv) { $csv = Join-Path $ws "data\samples\chips_seed.csv"; $env:CHIPS_CSV = $csv }
if (Test-Path $csv) {
  $n = (Get-Content $csv -Encoding UTF8).Count - 1
  Ok ("dataset: " + $csv + " (" + $n + " data rows)")
} else { Bad ("dataset missing: " + $csv) }

# --- 4. end-to-end --------------------------------------------------------
$e2e = Join-Path $ws "scripts\_check_e2e.py"
if (Test-Path $e2e) {
  $out2 = & $py $e2e 2>$null
  $out2 | ForEach-Object { Write-Host ("       " + $_) }
  if ($LASTEXITCODE -eq 0) { Ok "end-to-end pipeline works (part lookup + natural language)" }
  else { Bad "end-to-end failed -> python prototype\recommend.py STM32F103C8T6" }
} else { Warn ("probe not found: " + $e2e) }

# --- 5. regression tests --------------------------------------------------
# tests/ locks in the defects found by the offline evaluation (zero-tolerance
# hard constraints, temperature downgrade, ablation rewiring, tuple-index
# regression, tail-word stripping). Skipped with a warning if pytest is absent.
$tests = Join-Path $ws "tests"
& $py -c "import pytest" 2>$null
if ($LASTEXITCODE -ne 0) {
  Warn "pytest not installed - skipping regression tests (python scripts\fetch_deps.py --target .deps --only pytest,iniconfig,packaging,pluggy,pygments)"
} elseif (Test-Path $tests) {
  $out3 = & $py -m pytest $tests -q --no-header -p no:cacheprovider 2>&1
  $out3 | Select-Object -Last 6 | ForEach-Object { Write-Host ("       " + $_) }
  if ($LASTEXITCODE -eq 0) { Ok "regression tests pass (tests/)" }
  else { Bad "regression tests failed -> python -m pytest tests" }
} else { Warn ("tests directory not found: " + $tests) }

# --- 6. verdict -----------------------------------------------------------
Write-Host ""
if ($script:fail -eq 0) { Write-Host "ALL CHECKS PASSED"; exit 0 }
Write-Host ("CHECKS FAILED: " + $script:fail); exit 1
