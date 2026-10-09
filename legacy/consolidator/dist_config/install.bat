@echo off
REM install.bat - full install for iTunes Library Consolidator.
REM Run from anywhere; builds the venv, deps, tests, the .exe via
REM PyInstaller, then creates Desktop/Start Menu shortcuts and an
REM "Apps & features" uninstall entry. No Inno Setup required.

setlocal
cd /d "%~dp0.."
set "APP_DIR=%CD%"
set "DIST_FOLDER=%APP_DIR%\dist\iTunesLibraryConsolidator"
set "EXE_PATH=%APP_DIR%\iTunesLibraryConsolidator.exe"
set "ICON_PATH=%APP_DIR%\assets\app_icon.ico"

echo.
echo === iTunes Library Consolidator - Install ===
echo Project: %APP_DIR%
echo.

echo [1/6] Creating virtual environment...
python -m venv .venv
if errorlevel 1 (
    echo Failed to create virtual environment. Is Python 3.10+ on PATH?
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat

echo [2/6] Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency install failed.
    pause
    exit /b 1
)
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

echo [3/6] Generating test fixture...
python tests\generate_fixture.py
if errorlevel 1 (
    echo Could not generate test fixture - aborting.
    pause
    exit /b 1
)

echo [4/6] Running tests...
python tests\test_consolidation.py
if errorlevel 1 (
    echo Tests failed - aborting.
    pause
    exit /b 1
)

echo [5/6] Building executable with PyInstaller...
pyinstaller dist_config\build.spec --distpath dist --workpath build --noconfirm
if errorlevel 1 (
    echo PyInstaller build failed.
    pause
    exit /b 1
)
if not exist "%DIST_FOLDER%\iTunesLibraryConsolidator.exe" (
    echo Build finished but %DIST_FOLDER%\iTunesLibraryConsolidator.exe is missing.
    pause
    exit /b 1
)

REM Bug fix: "xcopy /y /q" (no /E or /S) does not recurse into
REM subfolders, so it only copied the exe and any loose files directly
REM inside DIST_FOLDER -- not the dependency subfolder (e.g. _internal\)
REM PyInstaller onedir mode (see build.spec's COLLECT) puts the actual
REM interpreter/library DLLs into. The exe would then run fine from
REM inside dist\iTunesLibraryConsolidator\ (where that subfolder sits
REM right next to it) but fail with a "module not found"-style error
REM when run from the project root, where that subfolder was never
REM copied. /E copies subfolders (including empty ones); /I tells xcopy
REM the destination is a directory even on the very first copy.
echo Copying built app to project root...
xcopy /y /q /e /i "%DIST_FOLDER%\*" "%APP_DIR%\" >nul
if not exist "%EXE_PATH%" (
    echo Build finished but %EXE_PATH% is missing.
    pause
    exit /b 1
)

echo [6/6] Creating shortcuts and uninstall entry...
REM Read the real app version from changelog.py rather than a hardcoded
REM literal here, which had drifted to "1.3.1" while the app moved on
REM through 1.3.2-1.3.9 -- showing a stale, wrong version under Apps &
REM features after every subsequent release. Falls back to "unknown" (never
REM blocks install) if the version string can't be parsed for any reason.
set "APP_VERSION=unknown"
for /f "usebackq delims=" %%V in (`python -c "import sys; sys.path.insert(0, '.'); from src.changelog import APP_VERSION; print(APP_VERSION)" 2^>nul`) do set "APP_VERSION=%%V"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'iTunes Library Consolidator.lnk'));" ^
    "$s.TargetPath = '%EXE_PATH%'; $s.WorkingDirectory = '%APP_DIR%';" ^
    "$iconPath = '%ICON_PATH%'; if (Test-Path $iconPath) { $s.IconLocation = $iconPath };" ^
    "$s.Description = 'iTunes Library Consolidator'; $s.Save()"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$startMenu = [Environment]::GetFolderPath('Programs');" ^
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([System.IO.Path]::Combine($startMenu, 'iTunes Library Consolidator.lnk'));" ^
    "$s.TargetPath = '%EXE_PATH%'; $s.WorkingDirectory = '%APP_DIR%';" ^
    "$iconPath = '%ICON_PATH%'; if (Test-Path $iconPath) { $s.IconLocation = $iconPath };" ^
    "$s.Description = 'iTunes Library Consolidator'; $s.Save()"

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\iTunesLibraryConsolidator" /f /v "DisplayName" /t REG_SZ /d "iTunes Library Consolidator" >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\iTunesLibraryConsolidator" /f /v "DisplayVersion" /t REG_SZ /d "%APP_VERSION%" >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\iTunesLibraryConsolidator" /f /v "Publisher" /t REG_SZ /d "iTunes Library Consolidator" >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\iTunesLibraryConsolidator" /f /v "InstallLocation" /t REG_SZ /d "%APP_DIR%" >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\iTunesLibraryConsolidator" /f /v "DisplayIcon" /t REG_SZ /d "%EXE_PATH%" >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\iTunesLibraryConsolidator" /f /v "UninstallString" /t REG_SZ /d "\"%APP_DIR%\dist_config\uninstall.bat\"" >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\iTunesLibraryConsolidator" /f /v "NoModify" /t REG_DWORD /d 1 >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\iTunesLibraryConsolidator" /f /v "NoRepair" /t REG_DWORD /d 1 >nul

echo.
echo Install complete. Launch from the Desktop or Start Menu shortcut.
echo.
pause
