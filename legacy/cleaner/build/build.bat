@echo off
REM ============================================================
REM GenreCleanup build script (run on Windows)
REM Ported from WhiteBoard's build\build.bat / build_progress.py /
REM build_menu.py / installer.iss / unblock.bat.
REM
REM Produces: GenreCleanup.exe (project root)
REM       and: dist_installer\GenreCleanup-Setup.exe (if Inno Setup installed)
REM
REM Run this from the PROJECT ROOT folder (the "pyport" folder, the one
REM containing "main.py" and "build\"):
REM     build\build.bat
REM
REM Opens a small menu popup first (see build\build_menu.py) offering
REM Start Build, Uninstall, or Fix Build. Choosing Start Build (or Fix
REM Build, which cleans up first) runs fully silently: the console window
REM stays minimized for the whole build, a small progress popup shows
REM live step progress + a coloured timer/progress bar (see
REM build\build_progress.py), and everything auto-closes the moment the
REM build finishes or fails - no key press required. On failure the
REM console briefly stays up so any error text is still readable before
REM it closes. The popup also has a Cancel button that stops the build
REM and cleans up only THIS run's own temp/build files (see :cancelled
REM below) - it never touches a venv or output from a previous
REM successful build.
REM
REM NOTE vs WhiteBoard: GenreCleanup is a flat project (main.py sits
REM directly in the project root, there's no separate "app\" folder) and
REM builds as a PyInstaller ONEFILE exe (see build\genrecleanup.spec),
REM so there's no dist\GenreCleanup\ folder to move - just one exe file.
REM ============================================================

setlocal enabledelayedexpansion

REM Pre-build menu popup (see build\build_menu.py): shown once, on the
REM very first invocation, BEFORE the minimized-relaunch below - it's a
REM GUI popup with no need for a console, and showing it before the
REM relaunch means the person sees it immediately on double-click rather
REM than after a console window has already flashed up. Skipped entirely
REM on the minimized re-invocation of this same script (GENRECLEANUP_BUILD_MINIMIZED
REM is set by then), so the menu is never shown twice for one run.
if not defined GENRECLEANUP_BUILD_MINIMIZED (
    cd /d "%~dp0\.."
    set "GENRECLEANUP_MENU_RESULT=%TEMP%\genrecleanup_build_menu_%RANDOM%%RANDOM%.txt"
    del "!GENRECLEANUP_MENU_RESULT!" >nul 2>nul
    where pythonw >nul 2>nul
    if !errorlevel!==0 (
        pythonw "%~dp0build_menu.py" "!GENRECLEANUP_MENU_RESULT!"
    ) else (
        python "%~dp0build_menu.py" "!GENRECLEANUP_MENU_RESULT!"
    )

    set "GENRECLEANUP_MENU_CHOICE="
    if exist "!GENRECLEANUP_MENU_RESULT!" (
        set /p GENRECLEANUP_MENU_CHOICE=<"!GENRECLEANUP_MENU_RESULT!"
    )
    del "!GENRECLEANUP_MENU_RESULT!" >nul 2>nul

    REM No choice (window closed, Escape, or tkinter/Python unavailable):
    REM treat exactly like a cancelled prompt - do nothing and exit
    REM quietly, same as build_progress.py's own Cancel behavior further
    REM down the pipeline.
    if not defined GENRECLEANUP_MENU_CHOICE (
        exit /b 0
    )

    if "!GENRECLEANUP_MENU_CHOICE!"=="FIX" (
        set "GENRECLEANUP_FIX_BUILD=1"
    )
)
REM goto is deliberately outside the "if not defined GENRECLEANUP_BUILD_MINIMIZED"
REM block above rather than nested inside it: a `goto` executed from
REM inside a parenthesized if-block can jump out mid-block before the
REM command parser has finished reading the rest of that block, which is
REM a well-known batch pitfall. Checking the choice again here, unnested,
REM avoids that entirely.
if "%GENRECLEANUP_MENU_CHOICE%"=="UNINSTALL" goto :uninstall

if not defined GENRECLEANUP_BUILD_MINIMIZED (
    set GENRECLEANUP_BUILD_MINIMIZED=1
    start "GenreCleanup Build" /min cmd /c "%~f0"
    exit /b 0
)

cd /d "%~dp0\.."

if defined GENRECLEANUP_FIX_BUILD (
    echo.
    echo Fix Build: cleaning virtual environment and build artifacts...
    rd /s /q venv >nul 2>nul
    rd /s /q dist >nul 2>nul
    rd /s /q build\work >nul 2>nul
    if exist GenreCleanup.exe del /f /q GenreCleanup.exe >nul 2>nul
    echo Done. Starting a fresh build.
    echo.
)

REM Status file the progress popup polls (see build\build_progress.py).
REM Unique per run via %RANDOM% so two builds started back-to-back never
REM read/write each other's status file, and so Cancel can identify
REM exactly which run's own temp/work files to remove.
set "GENRECLEANUP_RUN_ID=%RANDOM%%RANDOM%"
set "GENRECLEANUP_BUILD_STATUS=%TEMP%\genrecleanup_build_status_%GENRECLEANUP_RUN_ID%.txt"
REM PyInstaller's own console output is also teed to this log so the popup
REM can derive a real progress bar for step 2/3 from PyInstaller's actual
REM phase markers (see build_progress.py) instead of faking an animation
REM with no relation to how far the build has actually gotten.
set "GENRECLEANUP_PYI_LOG=%TEMP%\genrecleanup_pyinstaller_log_%GENRECLEANUP_RUN_ID%.txt"
REM Cancel signal file: the popup's Cancel button creates this; this
REM script (and the working-directory watchdog below) polls for it and
REM aborts as soon as it appears, without waiting on a fixed timer step.
set "GENRECLEANUP_CANCEL_FLAG=%TEMP%\genrecleanup_build_cancel_%GENRECLEANUP_RUN_ID%.txt"
del "%GENRECLEANUP_CANCEL_FLAG%" >nul 2>nul
echo STEP:0:Starting...> "%GENRECLEANUP_BUILD_STATUS%"

REM This cmd.exe's own PID is resolved via PowerShell so the popup's Cancel
REM button can target the right process tree. Walking up three hops from
REM PowerShell's own $PID (helper -> its throwaway parent cmd.exe from the
REM `for /f` backtick capture -> that cmd.exe's own parent) reaches the
REM long-lived cmd.exe that runs the rest of this script and everything
REM Cancel needs to stop - see WhiteBoard's build.bat for the full
REM explanation of why the more naive one- or two-hop versions are wrong.
set "GENRECLEANUP_SELF_PID="
where powershell >nul 2>nul
if %errorlevel%==0 (
    for /f "usebackq" %%P in (`powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $PID); $gp = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $p.ParentProcessId); $ggp = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $gp.ParentProcessId); $ggp.ProcessId"`) do set "GENRECLEANUP_SELF_PID=%%P"
)

REM Launch the progress popup as its own detached background process (if
REM Python/tkinter aren't available this is a silent no-op - see the
REM script's own header). Prefer pythonw.exe (no console at all) so the
REM popup's own interpreter never flashes a second console window; fall
REM back to a minimized python.exe if pythonw isn't on PATH.
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" /min pythonw "%~dp0build_progress.py" "%GENRECLEANUP_BUILD_STATUS%" "%GENRECLEANUP_PYI_LOG%" "%GENRECLEANUP_CANCEL_FLAG%" "%GENRECLEANUP_SELF_PID%"
) else (
    start "" /min python "%~dp0build_progress.py" "%GENRECLEANUP_BUILD_STATUS%" "%GENRECLEANUP_PYI_LOG%" "%GENRECLEANUP_CANCEL_FLAG%" "%GENRECLEANUP_SELF_PID%"
)

echo Project root: %cd%
if not exist main.py (
    echo ERROR: main.py not found. Make sure you run this as build\build.bat
    echo from the project root folder ^(the "pyport" folder, the one
    echo containing main.py and build\^).
    echo FAILED:Checking project folder> "%GENRECLEANUP_BUILD_STATUS%"
    goto :fail
)
if exist "%GENRECLEANUP_CANCEL_FLAG%" goto :cancelled

echo.
echo Step 1/4: Setting up virtual environment and installing dependencies...
echo STEP:1:Installing dependencies...> "%GENRECLEANUP_BUILD_STATUS%"

REM Reuse an existing venv instead of recreating it every run -- `python -m
REM venv` is a no-op-slow full interpreter copy even when nothing changed,
REM and pip below already only installs/upgrades what's actually missing.
if exist venv\Scripts\activate.bat (
    echo Existing virtual environment found, reusing it.
) else (
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment. Is Python installed and on PATH?
        echo FAILED:Creating virtual environment> "%GENRECLEANUP_BUILD_STATUS%"
        goto :fail
    )
)

call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment.
    echo FAILED:Activating virtual environment> "%GENRECLEANUP_BUILD_STATUS%"
    goto :fail
)

REM pip's own upgrade check (skipped below via --disable-pip-version-check)
REM and an unconditional `pip install --upgrade pip` both cost a network
REM round-trip on every single build for something that's almost never
REM actually needed. pip already skips reinstalling packages that satisfy
REM the requirement, so this only touches pip itself, and only when it's
REM missing entirely (fresh venv) rather than on every run.
python -m pip --version >nul 2>nul
if errorlevel 1 (
    python -m pip install --upgrade pip --disable-pip-version-check --no-input
    if errorlevel 1 (
        echo ERROR: pip bootstrap failed. Check your internet connection.
        echo FAILED:Installing pip> "%GENRECLEANUP_BUILD_STATUS%"
        goto :fail
    )
)

REM requirements.txt already lists pyinstaller (see requirements.txt), so
REM unlike WhiteBoard's build.bat there's no separate "pip install
REM pyinstaller" step here - this one install covers pywin32, requests,
REM and pyinstaller together.
pip install -r requirements.txt --disable-pip-version-check --no-input
if errorlevel 1 (
    echo ERROR: Failed to install requirements.txt ^(pywin32 / requests / pyinstaller^).
    echo FAILED:Installing dependencies> "%GENRECLEANUP_BUILD_STATUS%"
    goto :fail
)
if exist "%GENRECLEANUP_CANCEL_FLAG%" goto :cancelled

echo.
echo Step 2/4: Building executable with PyInstaller...
echo STEP:2:Running PyInstaller...> "%GENRECLEANUP_BUILD_STATUS%"
REM Output is teed to GENRECLEANUP_PYI_LOG (via PowerShell Tee-Object, kept
REM on-screen too) so the popup can read real phase progress out of it; if
REM Tee-Object isn't available for any reason this falls back to running
REM PyInstaller directly with no log, which just means the popup shows the
REM step label without a progress bar (see build_progress.py) -- the build
REM itself is unaffected either way.
REM Tee-Object buffers its writes internally and does not flush per line,
REM so the popup's log tailer could see no new bytes for long stretches of
REM PyInstaller's actual progress -- the bar looked stalled even though the
REM build was moving. Writing each line out through a StreamWriter with
REM AutoFlush=true (still also echoed to the console via Write-Host) keeps
REM the log file's on-disk contents current within one line of whatever
REM PyInstaller just printed, so the popup's progress bar advances live.
where powershell >nul 2>nul
if %errorlevel%==0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$w = New-Object System.IO.StreamWriter('%GENRECLEANUP_PYI_LOG%', $false); $w.AutoFlush = $true; try { pyinstaller build\genrecleanup.spec --distpath dist --workpath build\work --noconfirm 2>&1 | ForEach-Object { Write-Host $_; $w.WriteLine($_) }; exit $LASTEXITCODE } finally { $w.Close() }"
) else (
    pyinstaller build\genrecleanup.spec --distpath dist --workpath build\work --noconfirm
)
if errorlevel 1 (
    echo ERROR: PyInstaller build failed. See the output above for details.
    echo FAILED:Running PyInstaller> "%GENRECLEANUP_BUILD_STATUS%"
    goto :fail
)

REM Onefile build: the output IS the single exe, at dist\GenreCleanup.exe
REM directly - no dist\GenreCleanup\ folder to look inside (see
REM build\genrecleanup.spec, which passes binaries/zipfiles/datas straight
REM into EXE() with no COLLECT() call).
if not exist dist\GenreCleanup.exe (
    echo ERROR: Build reported success but dist\GenreCleanup.exe was not found.
    echo Check the PyInstaller output above for warnings/errors.
    echo FAILED:Verifying build output> "%GENRECLEANUP_BUILD_STATUS%"
    goto :fail
)
if exist "%GENRECLEANUP_CANCEL_FLAG%" goto :cancelled

echo.
echo SUCCESS: Executable built at dist\GenreCleanup.exe
echo.

echo Step 3/4: Attempting to build installer with Inno Setup...
echo STEP:3:Building installer...> "%GENRECLEANUP_BUILD_STATUS%"
REM Installer step runs BEFORE the exe is moved to the project root below,
REM since installer.iss reads its file from dist\GenreCleanup.exe
REM (relative to the project root) - see build\installer.iss.
where iscc >nul 2>nul
if %errorlevel%==0 (
    iscc build\installer.iss
    if errorlevel 1 (
        echo WARNING: Inno Setup compilation failed. The .exe above still works standalone.
    ) else (
        echo SUCCESS: Installer built at dist_installer\GenreCleanup-Setup.exe
    )
) else (
    echo Inno Setup ^(iscc^) not found on PATH - skipping installer build.
    echo Install Inno Setup from https://jrsoftware.org/isinfo.php
    echo Then run: iscc build\installer.iss
)
if exist "%GENRECLEANUP_CANCEL_FLAG%" goto :cancelled

echo.
echo Step 4/4: Moving GenreCleanup.exe to the project root and cleaning up...
echo STEP:4:Finalizing...> "%GENRECLEANUP_BUILD_STATUS%"

REM Move (not copy) the single onefile exe up to the project root, so the
REM end result is a self-contained GenreCleanup.exe the person can
REM double-click right where they extracted the project, next to its
REM existing GenreCleanup.ico (see the README-equivalent note in build.bat's
REM own original header about copying the icon next to it for shortcuts --
REM the icon already lives at the project root here, untouched, so no copy
REM step is needed). A previous root-level build is removed first so this
REM never leaves a stale exe mixed up with the new one. Much simpler than
REM WhiteBoard's equivalent step since there's no onedir folder of DLLs/
REM data files to move alongside it - just the one file.
if exist GenreCleanup.exe del /f /q GenreCleanup.exe >nul 2>nul
move /y dist\GenreCleanup.exe . >nul

if not exist GenreCleanup.exe (
    echo ERROR: Could not move GenreCleanup.exe to the project root.
    echo FAILED:Finalizing> "%GENRECLEANUP_BUILD_STATUS%"
    goto :fail
)

REM Clean build artifacts now that everything needed has been moved out of
REM them: dist\ (now empty/redundant) and build\work\ (PyInstaller's
REM intermediate workpath - large and never needed again after a
REM successful build). The venv is deliberately kept so the next build is
REM fast (see the "reuse an existing venv" step above).
rd /s /q dist >nul 2>nul
rd /s /q build\work >nul 2>nul

echo.
echo SUCCESS: GenreCleanup.exe is ready at %cd%\GenreCleanup.exe
echo.
echo Done.
echo DONE> "%GENRECLEANUP_BUILD_STATUS%"
REM Give the popup a brief moment to notice DONE and self-close before this
REM window disappears too, then clean up the status file and exit - no key
REM press required.
timeout /t 1 >nul
del "%GENRECLEANUP_BUILD_STATUS%" >nul 2>nul
del "%GENRECLEANUP_PYI_LOG%" >nul 2>nul
del "%GENRECLEANUP_CANCEL_FLAG%" >nul 2>nul

REM Auto-launch the freshly built app so "build and run" is one step.
REM Launched detached so this build window can still close itself
REM immediately afterward instead of waiting on the app to exit.
REM
REM Plain "start "" GenreCleanup.exe" is NOT used here: this whole script
REM is itself running inside a console that was relaunched with
REM "start /min" right at the top (see GENRECLEANUP_BUILD_MINIMIZED
REM above), which sets SW_SHOWMINNOACTIVE/STARTF_USESHOWWINDOW in that
REM console's own STARTUPINFO. A plain "start" here can inherit that same
REM minimized/inactive show-state for the new process's main window, so
REM GenreCleanup.exe would appear minimized (and without focus) the moment
REM it launches instead of opening normally in front of everything else.
REM PowerShell's Start-Process builds a fresh STARTUPINFO of its own and
REM lets the window state be set explicitly via -WindowStyle Normal,
REM sidestepping that inherited state entirely; it also activates the new
REM process's window, so the app opens focused, not just un-minimized.
where powershell >nul 2>nul
if %errorlevel%==0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%cd%\GenreCleanup.exe' -WindowStyle Normal" >nul 2>nul
) else (
    REM No PowerShell available - fall back to plain start rather than not
    REM launching the app at all; the app may open minimized in this rare
    REM fallback case, same as before.
    start "" "%cd%\GenreCleanup.exe"
)

endlocal
exit /b 0

:fail
REM The popup already saw the FAILED status and will self-close on its own
REM after briefly showing which step failed. Keep the console up just long
REM enough for the error text above to actually be read, then close
REM automatically - no key press required.
timeout /t 8 >nul
del "%GENRECLEANUP_BUILD_STATUS%" >nul 2>nul
del "%GENRECLEANUP_PYI_LOG%" >nul 2>nul
del "%GENRECLEANUP_CANCEL_FLAG%" >nul 2>nul
endlocal
exit /b 1

:cancelled
REM Reached only via an explicit cancel-flag check between steps (the
REM popup's Cancel button also kills this script's process tree directly,
REM so a build genuinely stuck inside a long step like PyInstaller is
REM stopped immediately rather than waiting for the next checkpoint).
REM Cleanup here removes only THIS run's own temp/partial-build files -
REM never a previous successful build's GenreCleanup.exe at the project
REM root, never the reusable venv\, and never another run's status/log
REM files (all are unique per run via %GENRECLEANUP_RUN_ID%).
echo.
echo Build cancelled.
rd /s /q build\work >nul 2>nul
rd /s /q dist >nul 2>nul
del "%GENRECLEANUP_BUILD_STATUS%" >nul 2>nul
del "%GENRECLEANUP_PYI_LOG%" >nul 2>nul
del "%GENRECLEANUP_CANCEL_FLAG%" >nul 2>nul
endlocal
exit /b 1

:uninstall
REM Reached from the pre-build menu's "Uninstall" choice, before the
REM minimized relaunch, so this always runs in a normal (visible) console -
REM appropriate here since Inno Setup's own uninstaller shows its own UI
REM anyway, unlike the silent build steps above.
REM
REM installer.iss registers this AppId (see [Setup] AppId= there) under
REM the current user's uninstall registry key under HKCU by default -
REM but see the PrivilegesRequired note below, since an elevated install
REM ends up under HKLM instead. installer.iss uses PrivilegesRequired=
REM lowest / DefaultDirName={autopf}, so a normal, non-elevated install
REM is a per-user one. Looking this up (instead of guessing an
REM install path) means this finds the real uninstaller wherever Inno
REM Setup actually put it, and does nothing at all if GenreCleanup was
REM never installed via the installer - a loose, hand-run GenreCleanup.exe
REM at the project root (from Step 4/4 above) is build OUTPUT, not an
REM installed copy, and is never touched by this.
REM
REM PrivilegesRequired=lowest means Inno Setup does not *require*
REM elevation, but it also does not forbid it: if the installer was ever
REM actually run elevated (a UAC prompt accepted, "Run as administrator",
REM etc.), Inno Setup registers the per-user uninstall entry under HKLM
REM instead of HKCU for that run. Checking only HKCU therefore reports
REM "nothing to uninstall" for a real, present install whenever it had
REM been installed elevated - both hives are checked here, HKCU first
REM (the common case), then HKLM, so either kind of install is found.
echo.
echo Looking for an installed copy of GenreCleanup...
set "GENRECLEANUP_UNINSTALL_SUBKEY=Software\Microsoft\Windows\CurrentVersion\Uninstall\{D4C3B2A1-7F6E-4A3B-9C2A-GENRECLEANUP1}_is1"
set "GENRECLEANUP_UNINSTALL_STRING="
for /f "usebackq tokens=2,*" %%A in (`reg query "HKCU\%GENRECLEANUP_UNINSTALL_SUBKEY%" /v UninstallString 2^>nul ^| findstr /i UninstallString`) do set "GENRECLEANUP_UNINSTALL_STRING=%%B"
if not defined GENRECLEANUP_UNINSTALL_STRING (
    for /f "usebackq tokens=2,*" %%A in (`reg query "HKLM\%GENRECLEANUP_UNINSTALL_SUBKEY%" /v UninstallString 2^>nul ^| findstr /i UninstallString`) do set "GENRECLEANUP_UNINSTALL_STRING=%%B"
)

if not defined GENRECLEANUP_UNINSTALL_STRING (
    echo No installed copy of GenreCleanup was found ^(nothing to uninstall^).
    echo If GenreCleanup is installed for all users rather than just this one,
    echo remove it from Windows Settings ^> Apps instead.
    timeout /t 5 >nul
    endlocal
    exit /b 0
)

echo Found installed copy. Launching its uninstaller...
start "" /wait %GENRECLEANUP_UNINSTALL_STRING%
echo Done.
timeout /t 3 >nul
endlocal
exit /b 0
