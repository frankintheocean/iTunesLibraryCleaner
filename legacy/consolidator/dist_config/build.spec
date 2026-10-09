# PyInstaller spec for iTunes Library Consolidator.
# Build on Windows with:  pyinstaller dist_config/build.spec
# (Run from the project root so relative paths resolve.)
#
# IMPORTANT: src/main.py uses package-relative imports (`from .changelog
# import ...`), so it cannot be analyzed/run as a bare script -- doing so
# raises "ImportError: attempted relative import with no known parent
# package" both when run directly (`python src/main.py`) and in the frozen
# .exe. We instead point Analysis at a tiny top-level launcher script that
# imports and calls src.main.main() as a proper package, which is the same
# thing `python -m src.main` does.

# -*- mode: python ; coding: utf-8 -*-

import os
import sys

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# This .spec file is run by PyInstaller from the `dist_config/` directory
# (per the documented `pyinstaller dist_config/build.spec` invocation), so
# the project root (one level up, containing the `src` package) must be put
# on sys.path here before collect_submodules('src') can find anything --
# otherwise it silently returns [] and the frozen build fails at runtime
# with "ModuleNotFoundError: No module named 'src'" even though pathex=['..']
# is set below (pathex only affects PyInstaller's own module search, not
# this spec script's own import machinery).
_SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SPEC_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Analysis() resolves its script path relative to the spec file's own
# directory (or CWD) -- NOT via pathex, which only affects PyInstaller's
# module search path for imports, not this initial script lookup. run_app.py
# lives in this same dist_config/ directory, so it must be referenced with
# an explicit path here; a bare 'run_app.py' silently resolves against CWD
# and breaks the build as soon as it's invoked from anywhere but
# dist_config/ itself (e.g. the documented `pyinstaller dist_config/build.spec`
# run from the project root).
_RUN_APP = os.path.join(_SPEC_DIR, "run_app.py")

# Force-include every module under src/ explicitly. run_app.py's static
# `from src.main import main` gets PyInstaller as far as the `src.main`
# module, but main.py's own relative imports (`from .ui.main_window import
# MainWindow`, etc.) are resolved at runtime, not always fully walked by
# the analyzer -- collect_submodules guarantees every module in the
# package is bundled regardless.
hidden_src_modules = collect_submodules('src')
if not hidden_src_modules:
    raise SystemExit(
        "Build aborted: collect_submodules('src') found nothing. "
        f"Expected the 'src' package at {_PROJECT_ROOT}/src -- run "
        "PyInstaller from the project root's dist_config folder as "
        "documented in the README, not from an unrelated working directory."
    )

_ICON_PATH = os.path.join(_PROJECT_ROOT, "assets", "app_icon.ico")

# UPX exclusions: UPX-compressing the CPython DLL (python3XX.dll) and a
# handful of other core runtime/Qt DLLs is a known cause of the frozen
# .exe failing to start with "Failed to load Python DLL ... LoadLibrary:
# The specified module could not be found." -- Windows' loader (and/or
# the PyInstaller bootloader's own LoadLibrary call for the Python DLL
# specifically) can fail against a UPX-packed copy even though the
# unpacked file loads fine and UPX itself reports success, so this is
# not caught at build time. This is distinct from any legitimate
# "missing DLL" cause (a genuinely absent dependency, wrong arch, etc.)
# -- see dist_config/installer_README.md/README.md troubleshooting for
# both. UPX still runs (upx=True below is unchanged) and still shrinks
# every other bundled DLL; only these are left uncompressed.
_UPX_EXCLUDE = [
    "python3*.dll",
    "vcruntime*.dll",
    "msvcp*.dll",
    "Qt6Core.dll",
    "Qt6Gui.dll",
    "Qt6Widgets.dll",
]

# pywin32's COM bindings (win32com, pythoncom, pywintypes) are used by
# core/itunes_com_sync.py for live iTunes updates on Windows, and are
# only ever imported lazily inside that module's functions (never at
# module import time) specifically so the rest of the app keeps working
# unfrozen/cross-platform even without pywin32 installed. Because those
# imports are deferred, PyInstaller's static analyzer can't discover them
# by walking imports the normal way -- hence listing them explicitly here,
# guarded so a non-Windows build environment (or one without pywin32
# installed) doesn't fail the whole build over an optional feature's deps.
_win32_hidden_imports: list[str] = []
if sys.platform == "win32":
    try:
        import win32com  # noqa: F401
        _win32_hidden_imports = ["win32com", "win32com.client", "pythoncom", "pywintypes"]
    except ImportError:
        # pywin32 not installed in this build environment: build proceeds
        # without it, same as any other machine that doesn't have it --
        # itunes_com_sync.py's own ImportError guard means the app still
        # runs fine, just without the live-sync feature available.
        pass

a = Analysis(
    [_RUN_APP],
    pathex=['..', _PROJECT_ROOT],
    binaries=[],
    # Bundle the icon file itself (not just use it for the .exe's own file
    # icon below) so the running app can also set it as the window/taskbar
    # icon at runtime via QIcon -- see src/main.py.
    datas=[(_ICON_PATH, 'assets')],
    hiddenimports=['PyQt6.sip'] + hidden_src_modules + _win32_hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy'],  # keep the exe lean
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Standalone-folder (onedir) build rather than onefile: exclude_binaries=True
# here + COLLECT below assembles dist/iTunesLibraryConsolidator/ containing
# the .exe alongside its dependent DLLs/resources as separate files, instead
# of a single self-extracting .exe that unpacks to a temp dir on every
# launch. Startup is faster and antivirus/file-lock false positives on the
# temp-extraction step (a recurring source of the "Access is denied"
# failures build.bat's :unlock_dist works around) are avoided -- the
# tradeoff is a folder to distribute instead of one file, which build.bat's
# post-build copy step (see build.bat) and setup.iss's [Files] section
# already account for.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='iTunesLibraryConsolidator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=_UPX_EXCLUDE,
    runtime_tmpdir=None,
    console=False,          # windowed app, no console popup
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(_PROJECT_ROOT, "assets", "app_icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=_UPX_EXCLUDE,
    name='iTunesLibraryConsolidator',
)
