@echo off
REM Builds the Windows .exe. Run this ON WINDOWS from the project root:
REM     dist_config\build_windows.bat
REM Requires Python 3.10+ installed and on PATH.

echo Creating virtual environment...
python -m venv .venv
call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt

echo Generating test fixture...
python tests\generate_fixture.py
if errorlevel 1 (
    echo Could not generate test fixture - aborting build.
    exit /b 1
)

echo Running tests before build...
python tests\test_consolidation.py
if errorlevel 1 (
    echo Tests failed - aborting build.
    exit /b 1
)

echo Building executable with PyInstaller...
pyinstaller dist_config\build.spec --distpath dist --workpath build --noconfirm

REM Bug fix: "xcopy /y /q" (no /E or /S) does not recurse into
REM subfolders, so it left the dependency subfolder PyInstaller onedir
REM mode (see build.spec's COLLECT) puts alongside the exe (e.g.
REM _internal\) uncopied. The root-copied exe would then fail with a
REM "module not found"-style error, while the exe still inside
REM dist\iTunesLibraryConsolidator\ (right next to that subfolder) ran
REM fine. /E copies subfolders (including empty ones); /I tells xcopy
REM the destination is a directory even on the very first copy.
echo Copying built app to project root...
xcopy /y /q /e /i "dist\iTunesLibraryConsolidator\*" ".\" >nul
if not exist "iTunesLibraryConsolidator.exe" (
    echo Build finished but iTunesLibraryConsolidator.exe is missing from the project root.
    exit /b 1
)

echo.
echo Build complete. Find iTunesLibraryConsolidator.exe in the project root.
echo.
echo Optional: to build a Windows installer (Start Menu shortcut, uninstaller,
echo file association) with Inno Setup 6, run:
echo     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" dist_config\setup.iss
echo See dist_config\installer_README.md for details.
pause
