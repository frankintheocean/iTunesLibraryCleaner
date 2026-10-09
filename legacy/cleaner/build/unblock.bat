@echo off
REM ============================================================
REM GenreCleanup - unblock.bat
REM (ported from WhiteBoard's build\unblock.bat)
REM
REM Windows tags files downloaded from the internet (e.g. inside a
REM zip you downloaded) with a "Mark of the Web". That's what makes
REM Windows show the "Windows protected your PC" / publisher warning
REM when you double-click build.bat straight after extracting it.
REM
REM This script clears that mark from every file in this project
REM folder so build.bat (and everything it produces) runs without
REM that warning. It does not disable Windows security features or
REM change any system-wide setting -- it only removes the flag from
REM these specific files, which is the same thing "Unblock" in the
REM file's Properties dialog does, just applied recursively.
REM
REM Run this ONCE after extracting the project, from the project
REM ROOT folder (the "pyport" folder, the one containing "main.py"
REM and "build\"):
REM     build\unblock.bat
REM ============================================================

setlocal

REM Relaunch minimized on first invocation, same as build.bat, so this
REM doesn't pop up a full-size console window either.
if not defined GENRECLEANUP_BUILD_MINIMIZED (
    set GENRECLEANUP_BUILD_MINIMIZED=1
    start "GenreCleanup Unblock" /min cmd /c "%~f0"
    exit /b 0
)

cd /d "%~dp0\.."

echo Project root: %cd%
if not exist main.py (
    echo ERROR: main.py not found. Make sure you run this as build\unblock.bat
    echo from the project root folder ^(the "pyport" folder, the one
    echo containing main.py and build\^).
    timeout /t 5 >nul
    exit /b 1
)

echo.
echo Removing "Mark of the Web" from all files in this folder...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Get-ChildItem -Path '.' -Recurse -File | Unblock-File -ErrorAction SilentlyContinue"

if errorlevel 1 (
    echo WARNING: PowerShell unblock step reported an error. You can also
    echo unblock files manually: right-click build.bat, choose Properties,
    echo then tick "Unblock" at the bottom of the General tab and click OK.
) else (
    echo Done. You can now run build.bat without the security warning.
)

timeout /t 3 >nul
endlocal
