$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not $IsWindows -and $env:OS -ne 'Windows_NT') { throw 'Build the installer on Windows 10/11 x64.' }
function Checked { param([scriptblock]$Command); & $Command; if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" } }
Checked { py -3.12 -m venv .venv }
$Python = Join-Path $PWD '.venv\Scripts\python.exe'
Checked { & $Python -m pip install -r requirements-lock-windows.txt }
Checked { npm ci }
Checked { & $Python -m pytest tests legacy/consolidator/tests -q }
Checked { npm test }
Checked { npm run build }
Checked { & $Python scripts/collect-licenses.py }
Checked { & $Python -m PyInstaller --noconfirm --clean --distpath build --workpath build/pyinstaller scripts/backend.spec }
if (-not (Test-Path 'build/backend/library-backend.exe')) { throw 'Bundled Python executable is missing.' }
Checked { npm run package:windows }
Write-Host 'Installer generated under dist/windows. Run the clean Windows validation checklist before distribution.'
