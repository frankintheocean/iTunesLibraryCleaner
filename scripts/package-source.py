from pathlib import Path
import hashlib
import json
import zipfile
root = Path(__file__).resolve().parents[1]
version = json.loads((root / 'package.json').read_text())['version']
out = root.parent / 'deliverables' / f'Unified-iTunes-Library-Manager-{version}.zip'
out.parent.mkdir(parents=True, exist_ok=True)
exclude={'.git','.venv','node_modules','__pycache__','.pytest_cache','.runtime','.codex','.agents'}
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
 for path in sorted(root.rglob('*')):
  relative=path.relative_to(root)
  if not path.is_file() or any(part in exclude for part in relative.parts) or path.suffix=='.pyc':continue
  # Keep the built frontend; exclude other build outputs unless an actual validated installer exists.
  if relative.parts[0] in ('dist', 'build'):continue
  archive.write(path,Path('Unified-iTunes-Library-Manager')/relative)
with zipfile.ZipFile(out) as archive:
 assert archive.testzip() is None
 assert {name.split('/')[0] for name in archive.namelist()}=={'Unified-iTunes-Library-Manager'}
 for record in json.loads((root/'docs/source-inventory.json').read_text()):
  parts=Path(record['path']).parts
  relative=Path('legacy')/('cleaner' if parts[0]=='LibraryCleaner' else 'consolidator')/Path(*parts[2:])
  stored=archive.read(str(Path('Unified-iTunes-Library-Manager')/relative))
  assert hashlib.sha256(stored).hexdigest()==record.get('published_sha256',record['sha256']),str(relative)

checksum=hashlib.sha256(out.read_bytes()).hexdigest()
out.with_suffix('.zip.sha256').write_text(checksum+'  '+out.name+'\n')
print(out)
print(out.stat().st_size,'bytes')
