from pathlib import Path
import hashlib
import json
root=Path(__file__).resolve().parents[1]
records=json.loads((root/'docs/source-inventory.json').read_text())
for record in records:
 parts=Path(record['path']).parts
 target=root/'legacy'/('cleaner' if parts[0]=='LibraryCleaner' else 'consolidator')/Path(*parts[2:])
 assert target.is_file(),str(target)
 assert hashlib.sha256(target.read_bytes()).hexdigest()==record.get('published_sha256', record['sha256']),str(target)
print(f'PASS: all {len(records)} supplied project files verified, including documented key removal and guide edits.')
