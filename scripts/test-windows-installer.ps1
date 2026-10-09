$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($env:OS -ne 'Windows_NT') { throw 'Installer validation requires Windows.' }
$Python = Join-Path $PWD '.venv\Scripts\python.exe'
$Installer = @(Get-ChildItem 'dist/windows' -Filter '*.exe' | Where-Object Name -NotLike '*Uninstall*')
if ($Installer.Count -ne 1) { throw 'Expected exactly one installer.' }
$Work = Join-Path ([IO.Path]::GetTempPath()) ('uilm-install-' + [guid]::NewGuid().ToString('N'))
$InstallDir = Join-Path $Work 'app'
$ReportDir = Join-Path $PWD 'build/validation'
New-Item -ItemType Directory -Force $Work,$ReportDir | Out-Null
$Sentinel = Join-Path $Work 'preserved-state/music-and-settings.txt'
New-Item -ItemType Directory -Force (Split-Path $Sentinel) | Out-Null
Set-Content -LiteralPath $Sentinel -Value 'Synthetic acceptance fixture; preserve across uninstall.'
$env:LIBRARY_MANAGER_DATA_DIR = Split-Path $Sentinel
function Install-App {
    # NSIS requires /D to be the final argument, with no quotes around the path.
    $p = Start-Process -FilePath $Installer[0].FullName -ArgumentList "/S /D=$InstallDir" -PassThru -Wait
    if ($p.ExitCode -ne 0) { throw "Installer failed: $($p.ExitCode)" }
}
function Check-Native { param([scriptblock]$Command); & $Command; if ($LASTEXITCODE -ne 0) { throw "Validation failed: $LASTEXITCODE" } }
try {
    Install-App
    $Backend = Join-Path $InstallDir 'resources/backend/library-backend.exe'
    $Desktop = Join-Path $InstallDir 'Unified iTunes Library Manager.exe'
    if (-not (Test-Path $Backend) -or -not (Test-Path $Desktop)) { throw 'Installation omitted required executables.' }
    Check-Native { & $Python scripts/smoke-bundle.py $Backend }
    $env:LIBRARY_MANAGER_ELECTRON_EXECUTABLE = $Desktop
    $env:LIBRARY_MANAGER_SCREENSHOT_DIR = $ReportDir
    $env:LIBRARY_MANAGER_DESKTOP_REPORT = Join-Path $ReportDir 'desktop.json'
    Check-Native { npm run test:desktop }
    $DesktopState = (Get-Content $env:LIBRARY_MANAGER_DESKTOP_REPORT -Raw | ConvertFrom-Json).state
    $StateDatabase = Join-Path $DesktopState 'manager.sqlite'
    $StateHash = (Get-FileHash $StateDatabase -Algorithm SHA256).Hash
    Remove-Item -LiteralPath $Backend
    Install-App
    if (-not (Test-Path $Backend)) { throw 'Reinstallation did not repair the deleted backend.' }
    Check-Native { & $Python scripts/smoke-bundle.py $Backend }
    $Uninstaller = @(Get-ChildItem $InstallDir -Filter 'Uninstall*.exe')
    if ($Uninstaller.Count -ne 1) { throw 'Uninstaller is missing.' }
    # _?= keeps NSIS in the installed directory and makes the process waitable.
    $p = Start-Process -FilePath $Uninstaller[0].FullName -ArgumentList "/S _?=$InstallDir" -Wait -PassThru
    if ($p.ExitCode -ne 0 -or (Test-Path $Desktop)) { throw 'Uninstallation did not remove the application.' }
    if (-not (Test-Path $Sentinel) -or -not (Test-Path $StateDatabase)) { throw 'Uninstall removed user state.' }
    if ((Get-FileHash $StateDatabase -Algorithm SHA256).Hash -ne $StateHash) { throw 'Uninstall changed user state.' }
    Install-App
    Check-Native { & $Python scripts/smoke-bundle.py $Backend }
    if (-not (Test-Path $Sentinel) -or (Get-FileHash $StateDatabase -Algorithm SHA256).Hash -ne $StateHash) { throw 'Reinstall changed user state.' }
    @{
        result = 'passed'; platform = [Environment]::OSVersion.VersionString
        checks = @('silent install','installed backend','packaged Electron workflow','repair deleted backend','uninstall','reinstall','external state preservation')
        live_com = 'not run: hosted runner has no interactive classic iTunes test library'
        signing = 'unsigned; no signing identity configured'
        commit = $env:GITHUB_SHA
    } | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $ReportDir 'installer.json')
} finally {
    Remove-Item Env:LIBRARY_MANAGER_ELECTRON_EXECUTABLE -ErrorAction SilentlyContinue
    Remove-Item Env:LIBRARY_MANAGER_DESKTOP_REPORT -ErrorAction SilentlyContinue
    Remove-Item Env:LIBRARY_MANAGER_SCREENSHOT_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:LIBRARY_MANAGER_DATA_DIR -ErrorAction SilentlyContinue
}
