# Run on Windows x64 using Python 3.12+. Relative paths resolve from the project root.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files
root = Path(SPECPATH).parent
legacy = root / 'legacy'
hidden = collect_submodules('backend') + collect_submodules('uvicorn') + collect_submodules('mutagen')
hidden += ['gui', 'genre_rules', 'itunes_com', 'cleanup_engine', 'album_merge', 'online_lookup', 'style', 'icons', 'tkinter', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets']
if sys.platform == 'win32': hidden += ['pythoncom', 'pywintypes', 'win32com.client', 'win32timezone']
# Include all original Consolidator modules so legacy interfaces load in frozen builds.
for p in (legacy / 'consolidator' / 'src').rglob('*.py'):
    relative = p.relative_to(legacy / 'consolidator' / 'src').with_suffix('')
    if relative.name not in ('__init__', 'main'): hidden.append('.'.join(relative.parts))
datas = [(str(legacy), 'legacy'), (str(root / 'CHANGELOG.md'), '.')]
a = Analysis([str(root / 'scripts' / 'backend_entry.py')], pathex=[str(root), str(legacy / 'cleaner'), str(legacy / 'consolidator' / 'src')], binaries=[], datas=datas, hiddenimports=hidden, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='library-backend', debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True, icon=str(root / 'resources' / 'app.ico') if sys.platform == 'win32' else None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='backend')
