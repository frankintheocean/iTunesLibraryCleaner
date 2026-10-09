"""Exercise an actual bundled backend, with a disposable library and auth token."""
import json
import os
import secrets
import queue
import threading
from collections import deque
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='uilm-bundle-smoke-') as folder:
 data=Path(folder)
 subprocess.run([sys.executable,str(root/'tests/make_fixture.py'),str(data/'fixture')],check=True)
 token=secrets.token_hex(32)
 process=subprocess.Popen([sys.argv[1],'--data-dir',str(data/'state')],env={**os.environ,'LIBRARY_MANAGER_TOKEN':token},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 stderr=deque(maxlen=100)
 def drain_errors():
  for line in process.stderr: stderr.append(line)
 errors=threading.Thread(target=drain_errors,daemon=True);errors.start()
 lines=queue.Queue()
 threading.Thread(target=lambda: lines.put(process.stdout.readline()),daemon=True).start()
 try:
  try: first=lines.get(timeout=45)
  except queue.Empty: raise RuntimeError('Bundled backend readiness timed out. '+''.join(stderr)[-8000:])
  if not first:
   errors.join(1)
   raise RuntimeError('Bundled backend exited before readiness. '+''.join(stderr)[-8000:])
  ready=json.loads(first);assert ready['ready']
  base=f"http://127.0.0.1:{ready['port']}"
  def request(path,body=None):
   payload=json.dumps(body).encode() if body is not None else None
   req=urllib.request.Request(base+path,data=payload,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
   with urllib.request.urlopen(req,timeout=15) as response:return json.load(response)
  assert request('/health')['version']=='3.1.1'
  if sys.platform=='win32':
   status=request('/com/status')
   reason=status.get('reason','')
   assert 'No module named' not in reason and 'DLL load failed' not in reason,reason
  result=request('/profiles',{'name':'Bundle validation','kind':'xml','source':str(data/'fixture/Library.xml')})
  deadline=time.monotonic()+15
  while time.monotonic()<deadline:
   jobs=request('/jobs')
   job=next(j for j in jobs if j['id']==result['job'])
   if job['status']=='complete':break
   if job['status']=='failed':raise AssertionError(job['error'])
   time.sleep(.1)
  else:raise AssertionError('Bundle scan did not complete')
  assert request(f"/profiles/{result['id']}/overview")['tracks']==120
  assert request(f"/profiles/{result['id']}/playlists")[0]['name']=='Evening favorites'
  assert request('/changelog')['text'] == (root / 'CHANGELOG.md').read_text(encoding='utf-8')
  print('PASS: bundled backend readiness, authenticated API, real 120-track XML scan, SQLite index, playlist and embedded changelog.')
 finally:
  process.terminate()
  try:process.wait(5)
  except subprocess.TimeoutExpired:process.kill();process.wait(5)
