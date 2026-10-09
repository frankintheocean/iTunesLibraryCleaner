$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($env:OS -ne 'Windows_NT') { throw 'Live COM validation requires Windows and classic iTunes.' }
function Checked { param([scriptblock]$Command); & $Command; if ($LASTEXITCODE -ne 0) { throw "Validation failed: $LASTEXITCODE" } }
if (-not (Test-Path '.venv/Scripts/python.exe')) { Checked { py -3.12 -m venv .venv } }
$Python = Join-Path $PWD '.venv/Scripts/python.exe'
Checked { & $Python -m pip install -r requirements-lock-windows.txt }
Checked { & $Python scripts/validate-live-com.py --empty-test-library }
