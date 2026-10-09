@echo off
REM build.bat - guided build for iTunes Library Consolidator.
REM
REM Flow: pre-build menu popup (choose whether to auto-launch on success)
REM -> relaunches itself minimized (same startup pattern as unblock.bat)
REM -> single progress popup, started once and kept open for the whole
REM 4-step build (deps, fixture+tests, PyInstaller build, done) -> auto-
REM launch the built .exe on success.
REM
REM The menu/progress popups (build_menu.py / build_progress.py) are
REM self-contained tkinter scripts run with the build venv's own Python;
REM if tkinter or a display isn't available they print one line and this
REM script proceeds using the console output alone, exactly as it would
REM without them. Nothing about the underlying build steps changes.
REM
REM Run from anywhere; equivalent build steps to install.bat's [1/6]-[5/6]
REM (venv, deps, fixture, tests, PyInstaller) without the shortcut/registry
REM install steps -- use install.bat instead if you also want Desktop/
REM Start Menu shortcuts and an Apps & features entry.

setlocal enabledelayedexpansion

REM Relaunch minimized on first invocation, same as unblock.bat, so
REM double-clicking this doesn't leave a full-size console window sitting
REM behind the popups for the rest of the build.
if not defined ITUNESCONSOLIDATOR_BUILD_MINIMIZED (
    set ITUNESCONSOLIDATOR_BUILD_MINIMIZED=1
    start "iTunes Library Consolidator Build" /min cmd /c "%~f0"
    exit /b 0
)

cd /d "%~dp0.."
set "APP_DIR=%CD%"
set "DIST_FOLDER=%APP_DIR%\dist\iTunesLibraryConsolidator"
set "BUILT_EXE_PATH=%DIST_FOLDER%\iTunesLibraryConsolidator.exe"
set "EXE_PATH=%APP_DIR%\iTunesLibraryConsolidator.exe"

REM Unique-per-run temp dir/files so overlapping or repeated runs (e.g. a
REM previous build.bat still finishing up) never share or clobber each
REM other's cancel-file, step-file, or PID state.
set "RUN_ID=%RANDOM%_%RANDOM%_%TIME::=%"
set "RUN_ID=%RUN_ID: =%"
set "BUILD_TMP=%TEMP%\ILC_build_%RUN_ID%"
mkdir "%BUILD_TMP%" >nul 2>&1
set "CANCEL_FILE=%BUILD_TMP%\cancel.flag"
set "MENU_RC_FILE=%BUILD_TMP%\menu.rc"
set "STEP_FILE=%BUILD_TMP%\step.txt"
set "PROGRESS_PID_FILE=%BUILD_TMP%\progress.pid"
set "PYINSTALLER_LOG=%BUILD_TMP%\pyinstaller.log"

set "PYTHON_EXE=python"
set "AUTO_LAUNCH=1"

REM --- Pre-build menu popup -------------------------------------------
REM Uses the system Python (venv doesn't exist yet at this point) purely
REM to show the tkinter popup; falls back to proceeding with defaults if
REM Python itself isn't on PATH, same silent-degrade contract as the venv
REM Python case inside build_menu.py.
where python >nul 2>&1
if errorlevel 1 (
    echo Python not found on PATH - skipping menu popup, using defaults.
    set "MENU_RC=0"
) else (
    python "%~dp0build_menu.py"
    set "MENU_RC=!ERRORLEVEL!"
)

if "!MENU_RC!"=="1" (
    echo Build cancelled.
    goto :cleanup_exit
)
if "!MENU_RC!"=="2" (
    set "AUTO_LAUNCH=0"
)

REM --- Step tracking / cancel helper -----------------------------------
set "TOTAL_STEPS=4"

REM Start the progress popup ONCE, in the background, before step 1, and
REM leave it running for the whole build. Bug fix: this used to be
REM relaunched as a new short-lived process per step that closed itself
REM on a fixed display timer regardless of how long the real step took,
REM so it never actually stayed open through a step. It now stays open
REM until :close_progress explicitly tells it to (on completion, cancel,
REM or failure) or the user clicks its own Cancel button.
call :set_step 1 "Setting up environment and installing dependencies"
call :start_progress
if exist "%CANCEL_FILE%" goto :cancelled

echo [1/4] Creating virtual environment and installing dependencies...
python -m venv .venv
if errorlevel 1 (
    echo Failed to create virtual environment. Is Python 3.10+ on PATH?
    goto :build_failed
)
call .venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency install failed.
    goto :build_failed
)
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller.
        goto :build_failed
    )
)
if exist "%CANCEL_FILE%" goto :cancelled

call :set_step 2 "Generating test fixture and running tests"
if exist "%CANCEL_FILE%" goto :cancelled

echo [2/4] Generating test fixture and running tests...
python tests\generate_fixture.py
if errorlevel 1 (
    echo Could not generate test fixture - aborting build.
    goto :build_failed
)
python tests\test_consolidation.py
if errorlevel 1 (
    echo Tests failed - aborting build.
    goto :build_failed
)
if exist "%CANCEL_FILE%" goto :cancelled

call :set_step 3 "Building executable with PyInstaller"
if exist "%CANCEL_FILE%" goto :cancelled

echo [3/4] Building executable with PyInstaller...

REM Clear any lock on the previous build's exe/dist folder (running
REM process, open Explorer window, antivirus scan, etc.) before
REM PyInstaller tries to delete/overwrite it -- avoids
REM "PermissionError: [WinError 5] Access is denied" on
REM dist\iTunesLibraryConsolidator.exe during the assemble step. (Folded
REM in from the former standalone unlock_dist.bat -- same logic, now a
REM local subroutine so there's one script to run/ship instead of two.)
call :unlock_dist
if errorlevel 1 (
    echo Could not clear the previous build output - aborting build.
    goto :build_failed
)
if exist "%CANCEL_FILE%" goto :cancelled

REM Also unlock and remove any OLD installed instances left on this
REM machine from a previous install.bat run (possibly in a different
REM project folder) -- see :remove_old_instances below. Best-effort and
REM never fails the build: an old instance some other tool still has
REM open, or nothing to find at all, just leaves it in place.
call :remove_old_instances
if exist "%CANCEL_FILE%" goto :cancelled

REM PyInstaller's own console output is tee'd to PYINSTALLER_LOG as it's
REM produced (PowerShell's Tee-Object, present on every supported Windows
REM version -- no new dependency) so it keeps streaming to this console
REM exactly as before, while the already-running progress popup tails the
REM same log file to advance its bar smoothly within this step (see
REM build_progress.py's --pyinstaller-log handling) instead of sitting
REM frozen on "3 of 4" for however long PyInstaller actually takes.
REM Deliberately NOT merging stderr into the piped stream (no "2>&1"
REM here): PowerShell wraps a native command's stderr lines as
REM ErrorRecord objects when merged this way, which Tee-Object then
REM reformats -- silently corrupting the plain-text phase lines this log
REM is tailed for, and risking a non-terminating error under some
REM PowerShell configurations. PyInstaller's own progress/phase output is
REM on stdout, so this is captured either way; stdout is also what a
REM normal (non-piped) run already shows here.
REM %TEMP% (and therefore PYINSTALLER_LOG) can contain spaces on a real
REM machine, so the path is single-quoted for PowerShell's own parser,
REM which treats single quotes as a literal string with no expansion.
REM Bug fix: the unescaped "&" inside this PowerShell -Command string
REM (i.e. "& pyinstaller ...") is, to cmd.exe's own parser, a command
REM separator character -- even though it's inside double quotes here,
REM cmd.exe's label-table scan (rebuilt when this script is re-invoked
REM via "cmd /c" at the top of this file for the minimized relaunch) can
REM mis-track quoting state around it. That desync is what caused
REM "The system cannot find the batch label specified - unlock_dist" a
REM few lines later at runtime -- cmd.exe's scan for :unlock_dist had
REM already gone wrong by the time it reached that label, even though
REM call :unlock_dist itself runs earlier, before this line. Wrapping
REM the PowerShell command in its own variable and calling powershell
REM with -Command %PS_CMD% (no inline "&...&" string for cmd.exe itself
REM to trip over) avoids the ambiguity entirely without changing what
REM PowerShell actually runs.
set "PS_CMD=& pyinstaller dist_config\build.spec --distpath dist --workpath build --noconfirm | Tee-Object -FilePath '%PYINSTALLER_LOG%'; exit $LASTEXITCODE"
powershell -NoProfile -Command "%PS_CMD%"
if errorlevel 1 (
    echo PyInstaller build failed.
    goto :build_failed
)
if not exist "%BUILT_EXE_PATH%" (
    echo Build finished but %BUILT_EXE_PATH% is missing.
    goto :build_failed
)
if exist "%CANCEL_FILE%" goto :cancelled

REM Copy the fully built .exe (and its dependent files -- PyInstaller's
REM onedir/standalone-folder mode, see build.spec, produces the .exe
REM alongside separate DLLs/resources rather than one self-contained
REM file) out of dist\iTunesLibraryConsolidator\ and into the project
REM root, so "the built .exe" is always found in the same, predictable
REM place (project root) regardless of build mode, instead of requiring
REM anyone to know to look inside dist\. xcopy /y overwrites in place;
REM the previous root copy (if any) was already unlocked/removed above
REM by :unlock_dist so this never fights a running instance.
REM Bug fix: "xcopy /y /q" (no /E or /S) only copies files directly
REM inside DIST_FOLDER -- it does NOT recurse into subfolders. PyInstaller
REM onedir mode (see build.spec's COLLECT) puts the interpreter/library
REM DLLs the exe actually needs at runtime into a subfolder alongside the
REM exe (e.g. _internal\), not loose next to it, so the old xcopy left
REM the root copy of the exe without its dependencies -- it ran fine from
REM inside dist\iTunesLibraryConsolidator\ (where that subfolder is right
REM next to it) but failed with a "module not found"-style popup when run
REM from the project root, where that subfolder was never copied over.
REM /E copies all subfolders including empty ones (/S alone skips empty
REM ones); /I tells xcopy the destination is a directory even the very
REM first time it's created (root copies of the last-run build already
REM removed just above by :unlock_dist).
echo Copying built app to project root...
xcopy /y /q /e /i "%DIST_FOLDER%\*" "%APP_DIR%\" >nul
if errorlevel 1 (
    echo Could not copy the built app to the project root.
    goto :build_failed
)
if not exist "%EXE_PATH%" (
    echo Build finished but %EXE_PATH% is missing after copying to the project root.
    goto :build_failed
)
if exist "%CANCEL_FILE%" goto :cancelled

call :set_step 4 "Build complete"
call :close_progress

echo [4/4] Build complete.
echo.
echo Find iTunesLibraryConsolidator.exe in the project root:
echo     %EXE_PATH%
echo.
echo Optional: to build a Windows installer, run:
echo     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" dist_config\setup.iss
echo See dist_config\installer_README.md for details.

if "%AUTO_LAUNCH%"=="1" (
    echo Launching iTunesLibraryConsolidator.exe...
    call :launch_in_focus
)

goto :cleanup_exit

REM --- Unlock/clear previous build output (formerly unlock_dist.bat) -----
REM Clears anything that could be holding a lock on the previous build
REM output before PyInstaller tries to overwrite it.
REM
REM Fixes: PermissionError: [WinError 5] Access is denied on
REM dist\iTunesLibraryConsolidator.exe during PyInstaller's assemble step
REM (os.remove(self.name)). That happens when the old .exe from a prior
REM build is still running, still open in Explorer, or still mid-scan by
REM antivirus, so Windows won't let PyInstaller delete it before writing
REM the new one.
REM
REM Called automatically from step [3/4] above, right before the
REM PyInstaller step. Never fails the build on its own: if a step here
REM can't do anything (e.g. nothing is running, or dist/build don't
REM exist yet) it just continues; it only returns errorlevel 1 (see
REM caller above) when a lock genuinely can't be cleared. Uses APP_DIR/
REM EXE_PATH already set at the top of this script rather than
REM recomputing them.
:unlock_dist
echo Clearing any locks on previous build output...

REM 1. Kill any running instance of the built exe (covers the exe being
REM    launched by a previous build.bat's auto-launch step, or manually
REM    from either the project root or the dist\ build folder).
tasklist /fi "imagename eq iTunesLibraryConsolidator.exe" 2>nul | find /i "iTunesLibraryConsolidator.exe" >nul
if not errorlevel 1 (
    echo   - iTunesLibraryConsolidator.exe is running, closing it...
    taskkill /im "iTunesLibraryConsolidator.exe" /f >nul 2>&1
    REM Give the OS a moment to actually release the file handle after
    REM the process exits before we try to touch/delete it below.
    timeout /t 1 >nul
)

REM 2. Remove old dist/build folders outright rather than trusting
REM    PyInstaller to overwrite in place. This also clears the case where
REM    a locking handle is held by something other than the exe itself
REM    (Explorer preview pane, a terminal cd'd into dist, antivirus scan
REM    still finishing) -- if the delete fails here, it fails fast with a
REM    clear message instead of deep inside PyInstaller's build.
if exist "%APP_DIR%\dist" (
    echo   - Removing previous dist folder...
    rd /s /q "%APP_DIR%\dist" >nul 2>&1
    if exist "%DIST_FOLDER%" (
        echo.
        echo Could not remove "%DIST_FOLDER%".
        echo It is likely still open in Explorer, a terminal, or locked by
        echo antivirus. Close whatever has it open ^(or add this project
        echo folder to your antivirus exclusions^) and run build.bat again.
        echo.
        exit /b 1
    )
)
if exist "%APP_DIR%\build" (
    echo   - Removing previous build folder...
    rd /s /q "%APP_DIR%\build" >nul 2>&1
)

REM 3. Remove the previous build's root-copied .exe too (see the
REM    post-build xcopy step in the main flow above) so a stale copy
REM    from an earlier build is never left sitting in the project root
REM    next to a newer, differently-shaped one -- and so xcopy below
REM    always writes a genuinely fresh copy rather than merging onto
REM    leftover files.
if exist "%EXE_PATH%" (
    echo   - Removing previous root copy of the built app...
    del /f /q "%EXE_PATH%" >nul 2>&1
    if exist "%EXE_PATH%" (
        echo.
        echo Could not remove "%EXE_PATH%".
        echo It is likely still open in Explorer, a terminal, or locked by
        echo antivirus. Close whatever has it open ^(or add this project
        echo folder to your antivirus exclusions^) and run build.bat again.
        echo.
        exit /b 1
    )
)

echo Done.
exit /b 0

REM --- Find/unlock/remove old installed instances -------------------------
REM Handles the separate case of an install.bat-installed copy of the app
REM elsewhere on this machine (a different project folder, or an older
REM checkout) -- distinct from :unlock_dist above, which only clears THIS
REM project's own dist\build folders before PyInstaller writes to them.
REM
REM install.bat records the install location in the registry under
REM HKCU\...\Uninstall\iTunesLibraryConsolidator ("InstallLocation" /
REM "DisplayIcon" -- see install.bat). This looks up that entry, kills any
REM running exe found there (same reasoning as :unlock_dist: a running
REM process/open Explorer window/antivirus scan can hold a file lock),
REM then deletes that old install's exe and shortcuts and clears the
REM registry entry so Apps & features doesn't keep pointing at a removed
REM copy.
REM
REM Never fails the build: every step here is best-effort (errors
REM suppressed with 2^>nul / ^>nul), since a leftover old instance
REM blocking removal shouldn't stop a fresh build of the current project
REM from completing.
:remove_old_instances
echo Looking for old installed instances on this system...

set "OLD_INSTALL_DIR="
set "OLD_EXE_PATH="
for /f "usebackq tokens=1,2*" %%A in (`reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\iTunesLibraryConsolidator" /v "InstallLocation" 2^>nul ^| findstr /i "InstallLocation"`) do (
    set "OLD_INSTALL_DIR=%%C"
)
for /f "usebackq tokens=1,2*" %%A in (`reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\iTunesLibraryConsolidator" /v "DisplayIcon" 2^>nul ^| findstr /i "DisplayIcon"`) do (
    set "OLD_EXE_PATH=%%C"
)

if not defined OLD_INSTALL_DIR (
    echo   - No previous install registration found.
    exit /b 0
)

REM Don't touch a registration that already points at THIS project's own
REM dist folder -- that copy is this project's current output, already
REM handled by :unlock_dist above, not an "old" instance.
if /i "%OLD_INSTALL_DIR%"=="%APP_DIR%" (
    echo   - Registered install is this project - nothing extra to remove.
    exit /b 0
)

echo   - Found a previous install at: %OLD_INSTALL_DIR%

REM 1. Kill any running instance of the old exe by full path (not just by
REM    image name, since a same-named exe from THIS build could otherwise
REM    be matched too) so its file handle is released before deletion.
if defined OLD_EXE_PATH (
    for /f "usebackq tokens=2 delims==" %%P in (
        `wmic process where "ExecutablePath='%OLD_EXE_PATH:\=\\%'" get ProcessId /value 2^>nul ^| findstr "="`
    ) do (
        echo     Closing old instance ^(PID %%P^)...
        taskkill /pid %%P /f >nul 2>&1
    )
    REM Fallback for any other process still holding that exe by image
    REM name alone, in case the WMI ExecutablePath match above didn't
    REM catch it (e.g. WMI unavailable in a locked-down environment).
    taskkill /fi "imagename eq iTunesLibraryConsolidator.exe" /fi "status eq running" /f >nul 2>&1
    timeout /t 1 >nul
)

REM 2. Delete the old install's exe/dist output and shortcuts. Best-effort
REM    -- a file still locked by something outside this app's control is
REM    skipped rather than failing the whole build.
if defined OLD_EXE_PATH if exist "%OLD_EXE_PATH%" (
    echo     Removing old executable...
    del /f /q "%OLD_EXE_PATH%" >nul 2>&1
)
if exist "%OLD_INSTALL_DIR%\dist" (
    echo     Removing old dist folder...
    rd /s /q "%OLD_INSTALL_DIR%\dist" >nul 2>&1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$desktop = [System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'iTunes Library Consolidator.lnk');" ^
    "$startMenu = [System.IO.Path]::Combine([Environment]::GetFolderPath('Programs'), 'iTunes Library Consolidator.lnk');" ^
    "foreach ($p in @($desktop, $startMenu)) { if (Test-Path $p) { Remove-Item $p -Force -ErrorAction SilentlyContinue } }" >nul 2>&1

REM 3. Clear the now-stale "Apps & features" registration so it stops
REM    pointing at a removed install. install.bat re-creates this entry
REM    (pointed at the current project) in its own [6/6] step, and this
REM    build.bat's caller may run install.bat separately afterward if
REM    shortcuts/registry entries are wanted for the new build too.
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\iTunesLibraryConsolidator" /f >nul 2>&1

echo   Done.
exit /b 0

REM --- Progress popup helpers --------------------------------------------
REM set_step rewrites STEP_FILE with the current step number/label; the
REM already-running popup process picks it up on its own poll (see
REM build_progress.py) -- no relaunch, no new process per step.
:set_step
(
    echo %~1
    echo %~2
) > "%STEP_FILE%"
exit /b 0

REM start_progress launches build_progress.py once, detached, and records
REM its PID so a Cancel click (which writes CANCEL_FILE) or an aborted
REM build can target this run's popup specifically if it's still open
REM (never another run's, since PROGRESS_PID_FILE is unique per run).
:start_progress
if exist "%PROGRESS_PID_FILE%" del /f /q "%PROGRESS_PID_FILE%" >nul 2>&1
start "" /min cmd /c "python "%~dp0build_progress.py" --step-file "%STEP_FILE%" --total %TOTAL_STEPS% --cancel-file "%CANCEL_FILE%" --pyinstaller-log "%PYINSTALLER_LOG%""
for /f "tokens=2" %%P in (
    'wmic process where "CommandLine like '%%build_progress.py%%%STEP_FILE:\=\\%%%'" get ProcessId ^| findstr /r "[0-9]"'
) do (
    echo %%P> "%PROGRESS_PID_FILE%"
)
exit /b 0

REM close_progress asks the still-running popup to exit cleanly (rather
REM than killing it) by writing the "close" sentinel to STEP_FILE; falls
REM back to taskkill only if that doesn't work, e.g. the popup process
REM already exited on its own (tkinter/display unavailable).
:close_progress
> "%STEP_FILE%" echo close
if exist "%PROGRESS_PID_FILE%" (
    for /f %%P in (%PROGRESS_PID_FILE%) do (
        timeout /t 1 >nul
        taskkill /pid %%P /f >nul 2>&1
    )
)
exit /b 0

REM launch_in_focus starts the freshly built app and brings its window to
REM the foreground. A plain "start" launches the process but doesn't
REM guarantee focus -- this whole script runs minimized (see the
REM self-relaunch at the top of this file), and depending on timing/focus-
REM stealing prevention in Windows, a newly started window can otherwise
REM open in the background behind whatever else is on screen, right after
REM a build the user is actively waiting on. Waits briefly for the main
REM window to exist, then calls SetForegroundWindow via the same P/Invoke
REM pattern already used in :build_failed to restore this console's own
REM window -- no new dependency.
:launch_in_focus
start "" "%EXE_PATH%"
powershell -NoProfile -WindowStyle Hidden -Command ^
    "$sig = '[DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr hWnd); [DllImport(\"user32.dll\")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);';" ^
    "$t = Add-Type -MemberDefinition $sig -Name Win32Focus -Namespace Console -PassThru;" ^
    "$proc = $null;" ^
    "for ($i = 0; $i -lt 20 -and -not $proc; $i++) {" ^
    "    Start-Sleep -Milliseconds 250;" ^
    "    $proc = Get-Process -Name 'iTunesLibraryConsolidator' -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1;" ^
    "}" ^
    "if ($proc) { $t::ShowWindow($proc.MainWindowHandle, 9) | Out-Null; $t::SetForegroundWindow($proc.MainWindowHandle) | Out-Null }" >nul 2>&1
exit /b 0

:cancelled
echo.
echo Build cancelled.
call :close_progress
if exist ".venv\Scripts\deactivate.bat" call .venv\Scripts\deactivate.bat >nul 2>&1
goto :cleanup_exit

:build_failed
call :close_progress
if exist ".venv\Scripts\deactivate.bat" call .venv\Scripts\deactivate.bat >nul 2>&1
REM Bug fix: on a failed build, delete the .venv outright instead of
REM just deactivating it. A build can fail partway through dependency
REM install (interrupted pip install, wrong Python on PATH, etc.),
REM leaving .venv on disk but incomplete/corrupt -- the next run's
REM "python -m venv .venv" silently no-ops against an existing folder,
REM so that broken venv would otherwise keep being reused and keep
REM failing build after build. Deleting it here guarantees the next
REM run starts from a clean venv. Best-effort: a locked file (e.g. an
REM editor still has one open) shouldn't block showing the real failure
REM reason/pause below.
if exist ".venv" (
    echo Removing .venv so the next build starts fresh...
    rd /s /q ".venv" >nul 2>&1
)
echo.
echo Build did not complete successfully.
REM This whole script runs in a /min (minimized, taskbar-only) window
REM (see the self-relaunch at the top of this file) so the in-progress
REM build stays out of the way. On failure that's a problem: a minimized
REM window with a pending "press any key" pause is easy to mistake for
REM the build having silently closed, since there's nothing visible on
REM screen. Restoring the window here (PowerShell driving the Win32
REM ShowWindow API on this console's own window handle -- no extra
REM dependency, present on every supported Windows version) makes sure
REM the failure and the pause prompt are actually seen instead of sitting
REM unnoticed in the taskbar.
powershell -NoProfile -WindowStyle Hidden -Command "$sig = '[DllImport(\"user32.dll\")] public static extern bool ShowWindow(int hWnd, int nCmdShow); [DllImport(\"kernel32.dll\")] public static extern int GetConsoleWindow();'; $t = Add-Type -MemberDefinition $sig -Name Win32 -Namespace Console -PassThru; $t::ShowWindow($t::GetConsoleWindow(), 9)" >nul 2>&1
pause
goto :cleanup_exit

:cleanup_exit
if exist "%BUILD_TMP%" rd /s /q "%BUILD_TMP%" >nul 2>&1
endlocal
exit /b 0
