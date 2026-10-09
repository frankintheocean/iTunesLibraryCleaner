from pathlib import Path
import hashlib
import json
import zipfile
import argparse
import subprocess
root = Path(__file__).resolve().parents[1]
version = json.loads((root / 'package.json').read_text())['version']

parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,default=root.parent/'deliverables')
args=parser.parse_args()
out = args.output_dir / f'iTunes-Manager-{version}-source.zip'
out.parent.mkdir(parents=True, exist_ok=True)
exclude={'.git','.venv','node_modules','__pycache__','.pytest_cache','.runtime','.codex','.agents'}
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
 for path in sorted(root.rglob('*')):
  relative=path.relative_to(root)
  if not path.is_file() or any(part in exclude for part in relative.parts) or path.suffix=='.pyc' or relative.as_posix()=='RELEASE-INFO.json':continue
  # Keep the built frontend; exclude other build outputs unless an actual validated installer exists.
  if relative.parts[0] in ('dist', 'build'):continue
  archive.write(path,Path('iTunes-Manager')/relative)
 commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
 archive.writestr('iTunes-Manager/RELEASE-INFO.json',json.dumps({'version':version,'source_commit':commit,'kind':'Source package'},indent=2)+'\n')
with zipfile.ZipFile(out) as archive:
 assert archive.testzip() is None
 assert {name.split('/')[0] for name in archive.namelist()}=={'iTunes-Manager'}
 for record in json.loads((root/'docs/source-inventory.json').read_text()):
  parts=Path(record['path']).parts
  relative=Path('legacy')/('cleaner' if parts[0]=='LibraryCleaner' else 'consolidator')/Path(*parts[2:])
  stored=archive.read((Path('iTunes-Manager')/relative).as_posix())
  assert hashlib.sha256(stored).hexdigest()==record.get('published_sha256',record['sha256']),str(relative)

checksum=hashlib.sha256(out.read_bytes()).hexdigest()
out.with_suffix('.zip.sha256').write_text(checksum+'  '+out.name+'\n')
print(out)
print(out.stat().st_size,'bytes')
