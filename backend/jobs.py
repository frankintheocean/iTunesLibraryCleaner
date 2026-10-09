import json
import threading
import time
import uuid
from .store import encode


class Cancelled(Exception): pass


class Jobs:
    """One mutation worker avoids concurrent writes to the same library or COM apartment."""
    def __init__(self, store, handler):
        self.store, self.handler = store, handler
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name='library-operations')
        self.thread.start()

    def enqueue(self, kind, payload, priority=0):
        identity = uuid.uuid4().hex; now = time.time()
        self.store.execute('INSERT INTO jobs(id,kind,payload,status,created,updated,priority) VALUES(?,?,?,?,?,?,?)', (identity, kind, encode(payload), 'queued', now, now, priority))
        self.wake.set()
        return identity

    def control(self, identity, action):
        rows = self.store.rows('SELECT * FROM jobs WHERE id=?', (identity,))
        if not rows: raise ValueError('Job not found.')
        job = rows[0]
        if action == 'cancel' and job['status'] in ('queued', 'running', 'paused'):
            self.store.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (identity,))
        elif action == 'pause' and job['status'] == 'running':
            self.store.execute("UPDATE jobs SET status='paused' WHERE id=?", (identity,))
        elif action == 'resume' and job['status'] == 'paused':
            self.store.execute("UPDATE jobs SET status='running' WHERE id=?", (identity,))
        elif action == 'retry' and job['status'] in ('failed', 'interrupted', 'cancelled'):
            if job['kind'] not in ('scan', 'transfer', 'verify'):
                raise ValueError('Obtain a new preview before retrying metadata or XML changes; the previous outcome may be partial.')
            payload = json.loads(job['payload']); payload['resume_from'] = job['checkpoint']
            payload['retry_of'] = identity
            return self.enqueue(job['kind'], payload, job['priority'])
        elif action in ('up', 'down') and job['status'] == 'queued':
            self.store.execute('UPDATE jobs SET priority=priority+? WHERE id=?', (1 if action == 'up' else -1, identity))
        else: raise ValueError('Action is not valid for this job state.')
        self.wake.set()
        return identity

    def checkpoint(self, job, done, total, current='', result=None):
        while True:
            if self.stop.is_set(): raise Cancelled('Shutdown requested at a safe boundary.')
            state = self.store.rows('SELECT status FROM jobs WHERE id=?', (job,))[0]['status']
            if state == 'cancelled': raise Cancelled('Cancelled at a safe boundary.')
            if state != 'paused': break
            self.stop.wait(.2)
        self.store.execute('UPDATE jobs SET checkpoint=?,progress=?,current=?,updated=? WHERE id=?', (done, done / max(total, 1) * 100, current, time.time(), job))

    def _run(self):
        while not self.stop.is_set():
            jobs = self.store.rows("SELECT * FROM jobs WHERE status='queued' ORDER BY priority DESC,created LIMIT 1")
            if not jobs:
                self.wake.wait(.5); self.wake.clear(); continue
            job = jobs[0]; identity = job['id']
            self.store.execute("UPDATE jobs SET status='running',updated=? WHERE id=?", (time.time(), identity))
            try:
                result = self.handler(job['kind'], json.loads(job['payload']), identity, self.checkpoint)
                self.store.execute("UPDATE jobs SET status='complete',progress=100,result=?,updated=? WHERE id=? AND status='running'", (encode(result), time.time(), identity))
                self.store.audit(job['kind'], {'job': identity, 'result': result})
            except Cancelled as exc:
                self.store.execute("UPDATE jobs SET status='interrupted',error=?,updated=? WHERE id=? AND status!='cancelled'", (str(exc), time.time(), identity))
            except Exception as exc:
                self.store.execute("UPDATE jobs SET status='failed',error=?,updated=? WHERE id=?", (str(exc), time.time(), identity))
                self.store.audit('failure', {'job': identity, 'error': str(exc)})

    def close(self):
        self.stop.set(); self.wake.set(); self.thread.join(5)
