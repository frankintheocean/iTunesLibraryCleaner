@echo off
REM uninstall.bat - removes shortcuts and the "Apps & features" entry
REM created by install.bat. Does not delete the exe, caches, or backups.

setlocal
echo.
echo === iTunes Library Consolidator - Uninstall ===
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$desktop = [System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'iTunes Library Consolidator.lnk');" ^
    "$startMenu = [System.IO.Path]::Combine([Environment]::GetFolderPath('Programs'), 'iTunes Library Consolidator.lnk');" ^
    "foreach ($p in @($desktop, $startMenu)) { if (Test-Path $p) { Remove-Item $p -Force } }"

reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\iTunesLibraryConsolidator" /f >nul 2>&1

echo Uninstalled. Your data, caches, and the exe are untouched.
echo.
pause
