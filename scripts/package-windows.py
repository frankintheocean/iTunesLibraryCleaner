"""Archive the complete Windows app; never ship an executable without its resources."""
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
version=json.loads((root/'package.json').read_text())['version']
folder=root/'dist/windows/win-unpacked'
required=['iTunes Manager.exe','resources/app.asar','resources/backend/library-backend.exe']
for name in required:
    if not (folder/name).is_file():raise SystemExit(f'Missing packaged app file: {name}')
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
output=folder.parent/f'iTunes-Manager-{version}-package-win-x64.zip'
with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for file in sorted(folder.rglob('*')):
        if file.is_file():archive.write(file,Path('iTunes-Manager')/file.relative_to(folder))
    archive.writestr('iTunes-Manager/RELEASE-INFO.json',json.dumps({'version':version,'source_commit':commit,'kind':'Windows app package'},indent=2)+'\n')
    archive.writestr('iTunes-Manager/START-HERE.txt',f'🎵 iTunes Manager {version}\n\nExtract the whole ZIP into a writable folder, then open iTunes Manager.exe.\nKeep its folders and support files together. Python and Node are not needed.\nSettings and backups use the same Windows AppData folder as the installer.\nLive edits need classic iTunes on Windows. The app is unsigned.\n')
with zipfile.ZipFile(output) as archive:
    assert archive.testzip() is None
    for name in required:assert 'iTunes-Manager/'+name in archive.namelist()
with output.open('rb') as file:checksum=hashlib.file_digest(file,'sha256').hexdigest()
output.with_suffix('.zip.sha256').write_text(checksum+'  '+output.name+'\n')
print(output)
