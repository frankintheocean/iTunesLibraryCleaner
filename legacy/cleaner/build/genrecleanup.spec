# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for GenreCleanup.
# Build with:  pyinstaller build/genrecleanup.spec
# Run from the project root (the folder containing "main.py" and "build\").
#
# This mirrors the previous plain CLI invocation
#     pyinstaller --onefile --windowed --icon=GenreCleanup.ico --name=GenreCleanup main.py
# as an explicit spec file (onefile: everything bundled directly into EXE,
# no COLLECT step / no onedir output folder) so build.bat can drive it the
# same way it drives PyInstaller for any other project in this family.

import os

block_cipher = None

project_root = os.getcwd()
icon_file = os.path.join(project_root, "GenreCleanup.ico")

a = Analysis(
    [os.path.join(project_root, "main.py")],
    pathex=[project_root],
    binaries=[],
    datas=[(icon_file, ".")],
    # pywin32's win32com is used for iTunes COM automation (see itunes_com.py).
    # PyInstaller ships a hook for pywin32 that handles most of this
    # automatically, but win32timezone is a common miss for COM-heavy
    # pywin32 apps, so it's listed explicitly rather than relying on the
    # hook alone.
    hiddenimports=["win32timezone"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Onefile build: a.binaries/a.zipfiles/a.datas are passed directly into EXE()
# (no COLLECT() call) so PyInstaller packs everything into a single
# GenreCleanup.exe rather than producing a dist\GenreCleanup\ folder.
# UPX left off for the same reason whiteboard.spec disables it: it can add
# real time to the build for a onefile desktop app with no meaningful
# runtime benefit, and can trigger false antivirus positives on packed
# binaries.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="GenreCleanup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)
