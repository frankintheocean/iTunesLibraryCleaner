from __future__ import annotations
import hashlib
import os
import re
import shutil
import string
import tempfile
import time
import uuid
from pathlib import Path

AUDIO = {'.mp3', '.m4a', '.m4b', '.aac', '.flac', '.ogg', '.opus', '.wav', '.aiff', '.aif', '.wma'}
RESERVED = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)}


def checked_path(value, exists=False):
    path = Path(value).expanduser().absolute()
    if '..' in path.parts:
        raise ValueError('Parent traversal is not allowed.')
    for component in (path, *path.parents):
        if component.is_symlink() or (hasattr(component, 'is_junction') and component.is_junction()):
            raise ValueError('Symlinks and junctions require manual review.')
    if exists and not path.exists(): raise ValueError(f'Path is unavailable: {path}')
    return path.resolve()


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def signature(path):
    p = checked_path(path, True)
    stat = p.stat()
    return {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns, 'sha256': digest(p)}


def safe_component(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value)).strip().rstrip('. ')
    value = value[:160] or 'Unknown'
    if value.split('.')[0].upper() in RESERVED: value = '_' + value
    return value


def organized_path(template, values, suffix):
    allowed = {'artist', 'album', 'album_artist', 'year', 'track', 'title', 'genre'}
    formatter = string.Formatter()
    for _, field, spec, conversion in formatter.parse(template):
        if field is not None and (field not in allowed or spec or conversion):
            raise ValueError('Template contains unsupported variables or formatting.')
    parts = template.replace('\\', '/').split('/')
    if any(p in ('', '.', '..') for p in parts): raise ValueError('Invalid organization template.')
    rendered = [safe_component(p.format(**{k: safe_component(values.get(k, 'Unknown')) for k in allowed})) for p in parts]
    return Path(*rendered).with_suffix(suffix.lower()) if Path(rendered[-1]).suffix == suffix.lower() else Path(*rendered[:-1], rendered[-1] + suffix.lower())


def verified_transfer(source, destination, expected, mode, store, job):
    source = checked_path(source, True)
    destination = checked_path(destination)
    if source == destination or destination.exists(): raise ValueError('Destination already exists; no overwrite is permitted.')
    if signature(source) != expected: raise ValueError('Source changed after preview.')
    ancestor = destination.parent
    while not ancestor.exists(): ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < expected['size'] + 16 * 1024 * 1024:
        raise ValueError('Insufficient destination disk space.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    identity = uuid.uuid4().hex
    store.execute('INSERT INTO transfers VALUES(?,?,?,?,?,?,?,?)', (identity, job, str(source), str(destination), expected['sha256'], mode, 'pending', time.time()))
    fd, staging = tempfile.mkstemp(prefix='.uilm-', dir=destination.parent)
    os.close(fd)
    try:
        shutil.copy2(source, staging)
        # Windows _commit (os.fsync) requires a writable descriptor.
        with open(staging, 'r+b') as f: os.fsync(f.fileno())
        if digest(staging) != expected['sha256']: raise ValueError('Copied file hash mismatch.')
        # Staging and destination share a filesystem. Hard-link creation atomically
        # publishes a complete file and fails if a filename was reserved concurrently.
        # Filesystems without this capability fail safely instead of exposing partial files.
        os.link(staging, destination)
        if digest(destination) != expected['sha256']: raise ValueError('Final file hash mismatch; source retained.')
        store.execute("UPDATE transfers SET status='copied' WHERE id=?", (identity,))
        if mode in ('move', 'quarantine', 'restore'):
            if signature(source) != expected: raise ValueError('Source changed during transfer; both files retained.')
            source.unlink()
        store.execute("UPDATE transfers SET status='complete' WHERE id=?", (identity,))
        return identity
    finally:
        Path(staging).unlink(missing_ok=True)
