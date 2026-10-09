"""Collect installed notices before bundling (does not infer missing licenses)."""
from pathlib import Path
from importlib.metadata import distributions
import json
import shutil

root = Path(__file__).resolve().parents[1]
out = root / 'resources' / 'licenses'
out.mkdir(parents=True, exist_ok=True)
records = []
for distribution in distributions():
    name = distribution.metadata.get('Name', 'unknown')
    copied = []
    for file in distribution.files or []:
        filename = Path(str(file)).name.lower()
        if any(word in filename for word in ('license', 'licence', 'copying', 'notice')):
            source = Path(distribution.locate_file(file))
            if source.is_file():
                relative = Path('python') / name / str(file).replace('..', '_')
                target = out / relative; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target); copied.append(str(relative))
    records.append({'package': name, 'version': distribution.version, 'license_expression': distribution.metadata.get('License-Expression'), 'notices': copied})
modules = root / 'node_modules'
for manifest in modules.rglob('package.json'):
    if '.cache' in manifest.parts: continue
    try: info = json.loads(manifest.read_text(encoding='utf-8'))
    except (ValueError, OSError): continue
    if not info.get('name') or not info.get('version'): continue
    copied = []
    for source in manifest.parent.iterdir():
        if source.is_file() and any(word in source.name.lower() for word in ('license', 'licence', 'copying', 'notice')):
            relative = Path('npm') / manifest.parent.relative_to(modules) / source.name
            target = out / relative; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target); copied.append(str(relative))
    records.append({'package': info['name'], 'version': info['version'], 'license_expression': info.get('license'), 'notices': copied})
(out / 'manifest.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
print(f'Collected notices for {len(records)} installed packages.')
