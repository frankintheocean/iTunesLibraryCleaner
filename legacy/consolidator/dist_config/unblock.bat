@echo off
REM unblock.bat - removes the Windows "Mark of the Web" from files in this
REM project (added automatically when downloaded/extracted from a zip),
REM which is what causes the "Windows protected your PC" / security
REM warning screen when running install.bat or build_windows.bat.
REM
REM Run this once, right after extracting the zip, before running
REM install.bat.

setlocal

REM Relaunch minimized on first invocation (same startup behavior as
REM WhiteBoard's unblock.bat) so double-clicking this doesn't pop up a
REM full-size console window.
if not defined ITUNESCONSOLIDATOR_UNBLOCK_MINIMIZED (
    set ITUNESCONSOLIDATOR_UNBLOCK_MINIMIZED=1
    start "iTunes Library Consolidator Unblock" /min cmd /c "%~f0"
    exit /b 0
)

cd /d "%~dp0.."
set "APP_DIR=%CD%"

echo.
echo === Unblocking project files in: %APP_DIR% ===
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Get-ChildItem -Path '%APP_DIR%' -Recurse -File | Unblock-File -ErrorAction SilentlyContinue"

if errorlevel 1 (
    echo WARNING: some files may not have been unblocked. You can also
    echo unblock files manually: right-click install.bat, choose Properties,
    echo then tick "Unblock" at the bottom of the General tab and click OK.
) else (
    echo Done. All files unblocked - the security warning should no longer appear.
)

timeout /t 3 >nul
endlocal
