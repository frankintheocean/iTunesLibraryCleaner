from __future__ import annotations
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path


def encode(value):
    return json.dumps(value, ensure_ascii=False, default=str)


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY);
            INSERT OR IGNORE INTO migrations VALUES(1);
            CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY, name TEXT NOT NULL, config TEXT NOT NULL, scanned REAL);
            CREATE TABLE IF NOT EXISTS tracks(profile TEXT, id INTEGER, pid TEXT, name TEXT, artist TEXT, album TEXT, genre TEXT, path TEXT, missing INTEGER, raw TEXT, PRIMARY KEY(profile,id));
            CREATE INDEX IF NOT EXISTS track_search ON tracks(profile,artist,name);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS previews(id TEXT PRIMARY KEY, kind TEXT, profile TEXT, payload TEXT, created REAL, consumed INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT, payload TEXT, status TEXT, progress REAL DEFAULT 0, current TEXT DEFAULT '', result TEXT, error TEXT, created REAL, updated REAL, priority INTEGER DEFAULT 0, checkpoint INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS history(id TEXT PRIMARY KEY, kind TEXT, detail TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS edits(id TEXT PRIMARY KEY, job TEXT, pid TEXT, target TEXT, field TEXT, old TEXT, new TEXT, status TEXT, error TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS transfers(id TEXT PRIMARY KEY, job TEXT, source TEXT, destination TEXT, hash TEXT, mode TEXT, status TEXT, created REAL);
            ''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(jobs)')}
            for name, definition in {'archived': 'INTEGER DEFAULT 0', 'started': 'REAL', 'finished': 'REAL', 'elapsed': 'REAL DEFAULT 0', 'active_since': 'REAL'}.items():
                if name not in columns: db.execute(f'ALTER TABLE jobs ADD COLUMN {name} {definition}')
            db.execute('INSERT OR IGNORE INTO migrations VALUES(2)')
            db.execute("UPDATE jobs SET elapsed=elapsed+MAX(0,updated-active_since),active_since=NULL,finished=updated WHERE active_since IS NOT NULL AND status IN ('running','paused')")
            db.execute("UPDATE jobs SET status='interrupted', error='Process stopped. Inspect checkpoint before retrying.' WHERE status IN ('running','paused')")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=30000')
        return db

    def rows(self, sql, args=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def execute(self, sql, args=()):
        with self.connect() as db:
            return db.execute(sql, args).rowcount

    def setting(self, key, default=None):
        rows = self.rows('SELECT value FROM settings WHERE key=?', (key,))
        return json.loads(rows[0]['value']) if rows else default

    def set_setting(self, key, value):
        self.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, encode(value)))

    def audit(self, kind, detail):
        self.execute('INSERT INTO history VALUES(?,?,?,?)', (uuid.uuid4().hex, kind, encode(detail), time.time()))

    def journal(self, job, pid, target, field, old, new):
        identity = uuid.uuid4().hex
        self.execute('INSERT INTO edits VALUES(?,?,?,?,?,?,?,?,?,?)',
                     (identity, job, pid, target, field, encode(old), encode(new), 'pending', '', time.time()))
        return identity

    def finish_edit(self, identity, status, error=''):
        self.execute('UPDATE edits SET status=?,error=? WHERE id=?', (status, error, identity))
