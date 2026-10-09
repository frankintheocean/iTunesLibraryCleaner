from __future__ import annotations
import base64
import copy
import json
import os
import plistlib
import shutil
import sqlite3
import stat as file_stat
import tempfile
import time
import uuid
import threading
import subprocess
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
import mutagen
from . import legacy, metadata
from .com_service import FIELDS, run_com, validate_fields, split_pid
from .filesystem import AUDIO, checked_path, signature, digest, organized_path, verified_transfer, safe_component
from .store import Store, encode
from .jobs import Jobs
from .lastfm import LastFM


class Service:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.store = Store(self.data_dir / 'manager.sqlite')
        self.lastfm = LastFM(self.store)
        self._library_lock = threading.RLock()
        self._libraries = {}
        self._overviews = {}
        self._index_versions = defaultdict(int)
        legacy.configure_rules(self.data_dir)
        self.jobs = Jobs(self.store, self.run_job)
        self.scheduler = threading.Thread(target=self.schedule, daemon=True, name='scan-scheduler')
        self.scheduler.start()

    def schedule(self):
        while not self.jobs.stop.wait(20):
            for row in self.store.rows('SELECT * FROM profiles'):
                config = json.loads(row['config']); minutes = config.get('scan_interval_minutes', 0)
                if config.get('removed'): continue
                if minutes and row['scanned'] and time.time() - row['scanned'] >= minutes * 60:
                    pending = self.store.rows("SELECT payload FROM jobs WHERE kind='scan' AND status IN ('queued','running','paused')")
                    if not any(json.loads(j['payload']).get('profile') == row['id'] for j in pending):
                        last = self.store.rows("SELECT created FROM jobs WHERE kind='scan' AND payload LIKE ? ORDER BY created DESC LIMIT 1", ('%' + row['id'] + '%',))
                        if not last or time.time() - last[0]['created'] >= minutes * 60:
                            self.jobs.enqueue('scan', {'profile': row['id']})

    def profile(self, identity):
        rows = self.store.rows('SELECT * FROM profiles WHERE id=?', (identity,))
        if not rows: raise ValueError('Library profile not found.')
        result = rows[0]; result['config'] = json.loads(result['config']); return result

    def snapshot_path(self, identity):
        config = self.profile(identity)['config']
        name = config.get('_snapshot', 'snapshot.xml')
        if Path(name).name != name: raise ValueError('Invalid saved library path.')
        return self.data_dir / 'libraries' / identity / name

    def library(self, identity, mutable=True):
        with self._library_lock:
            p = self.snapshot_path(identity)
            if not p.exists(): raise ValueError('Scan this library first.')
            stat = p.stat(); key = (str(p), stat.st_mtime_ns, stat.st_size)
            cached = self._libraries.get(identity)
            if not cached or cached[0] != key:
                cached = (key, legacy.Library.load(p))
                self._libraries[identity] = cached
                if len(self._libraries) > 8:
                    self._libraries.pop(next(iter(self._libraries)))
            return copy.deepcopy(cached[1]) if mutable else cached[1]

    def save_snapshot(self, identity, library, prepared_path=None):
        path = self.snapshot_path(identity)
        path.parent.mkdir(parents=True, exist_ok=True)
        if prepared_path:
            temp = str(prepared_path)
        else:
            fd, temp = tempfile.mkstemp(dir=path.parent, suffix='.xml')
            os.close(fd)
        try:
            if prepared_path:
                # XML scans already parsed this exact private staging file.
                verified = library
            else:
                library.save(Path(temp))
                verified = legacy.Library.load(Path(temp))
                with open(temp, 'rb+') as saved: os.fsync(saved.fileno())
            # Readers, iTunes and Windows scanners can hold an old XML open.
            # Publish a new file, then switch the SQLite pointer; never overwrite it.
            target = path.parent / ('snapshot-' + uuid.uuid4().hex + '.xml')
            for attempt in range(5):
                try:
                    os.replace(temp, target)
                    break
                except PermissionError:
                    if attempt == 4: raise
                    time.sleep(.05 * 2**attempt)
            verified.source_path = target
            with self._library_lock:
                profile = self.profile(identity)
                profile['config']['_snapshot'] = target.name
                self.store.execute('UPDATE profiles SET config=? WHERE id=?', (encode(profile['config']), identity))
                stat = target.stat()
                self._libraries[identity] = ((str(target), stat.st_mtime_ns, stat.st_size), verified)
                if len(self._libraries) > 8: self._libraries.pop(next(iter(self._libraries)))
                self._overviews.pop(identity, None)
            # Keep one previous snapshot for recovery. Locked old files can wait.
            for old in path.parent.glob('snapshot*.xml'):
                if old not in (path, target):
                    try: old.unlink()
                    except OSError: pass
        finally:
            try: Path(temp).unlink(missing_ok=True)
            except OSError: pass

    def add_profile(self, name, source, kind, roots=None):
        if kind not in ('xml', 'folder', 'live'): raise ValueError('Choose XML, media folder, or live iTunes.')
        if kind != 'live': checked_path(source, True)
        identity = uuid.uuid4().hex
        config = {'source': source, 'kind': kind, 'roots': roots or ([source] if kind == 'folder' else []), 'exclusions': [], 'scan_interval_minutes': 0}
        self.store.execute('INSERT INTO profiles VALUES(?,?,?,NULL)', (identity, name, encode(config)))
        return identity

    def index_rows(self, identity, library):
        rows = []; paths = {}
        for tid, track in library.tracks.items():
            path = legacy.file_uri_to_path(track.location or '')
            key = str(path or '')
            if key not in paths:
                try:
                    candidate = path.stat() if path else None
                    paths[key] = candidate if candidate and file_stat.S_ISREG(candidate.st_mode) else None
                except OSError: paths[key] = None
            stat = paths[key]
            missing = int(bool(path) and stat is None)
            if not track.raw.get('Size') and stat is not None:
                track.raw['Size'] = stat.st_size
            rows.append((identity, tid, track.raw.get('Persistent ID', ''), track.name, track.artist, track.album, track.raw.get('Genre', ''), str(path or ''), missing, encode(track.raw)))
        return rows

    def index(self, identity, library, rows=None):
        rows = self.index_rows(identity, library) if rows is None else rows
        with self.store.connect() as db:
            db.execute('DELETE FROM tracks WHERE profile=?', (identity,))
            db.executemany('INSERT INTO tracks VALUES(?,?,?,?,?,?,?,?,?,?)', rows)
            db.execute('DELETE FROM track_text WHERE profile=?', (identity,))
            db.execute('INSERT INTO track_text(rowid,profile,id,name,artist,album,genre) SELECT rowid,profile,id,name,artist,album,genre FROM tracks WHERE profile=?', (identity,))
            db.execute('UPDATE profiles SET scanned=? WHERE id=?', (time.time(), identity))
        self._overviews.pop(identity, None)
        self._index_versions[identity] += 1

    def index_changes(self, identity, tracks):
        """Refresh only edited rows. A one-song edit must not stat every media file."""
        with self.store.connect() as db:
            for track in tracks:
                raw = track.raw; tid = track.track_id
                previous = db.execute('SELECT rowid,raw FROM tracks WHERE profile=? AND id=?',(identity,tid)).fetchone()
                if not previous: raise ValueError('Edited track is no longer in the saved index.')
                if not raw.get('Size'): raw['Size'] = json.loads(previous['raw']).get('Size', 0)
                db.execute('UPDATE tracks SET name=?,artist=?,album=?,genre=?,raw=? WHERE profile=? AND id=?', (track.name,track.artist,track.album,raw.get('Genre',''),encode(raw),identity,tid))
                db.execute('DELETE FROM track_text WHERE rowid=?', (previous['rowid'],))
                db.execute('INSERT INTO track_text(rowid,profile,id,name,artist,album,genre) VALUES(?,?,?,?,?,?,?)', (previous['rowid'],identity,tid,track.name,track.artist,track.album,raw.get('Genre','')))
        self._overviews.pop(identity, None)
        self._index_versions[identity] += 1

    def remove_profile(self, identity):
        profile = self.profile(identity)
        pending = self.store.rows("SELECT payload FROM jobs WHERE status IN ('queued','running','paused')")
        if any(json.loads(row['payload']).get('profile') == identity for row in pending):
            raise ValueError('Wait for this library’s tasks to finish, or cancel them first.')
        profile['config']['removed'] = True
        self.store.execute('UPDATE profiles SET config=? WHERE id=?', (encode(profile['config']),identity))
        self._libraries.pop(identity, None); self._overviews.pop(identity, None)
        self.store.audit('library_removed', {'profile':identity,'name':profile['name']})
        return {'removed': True}

    def scan(self, identity, job, progress):
        profile = self.profile(identity); config = profile['config']; kind = config['kind']
        if config.get('removed'): raise ValueError('This library was removed from the app. Add it again to scan it.')
        prepared = None
        if kind == 'xml':
            source = checked_path(config['source'], True)
            folder = self.snapshot_path(identity).parent; folder.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(dir=folder, suffix='.xml'); os.close(fd)
            prepared = Path(name)
            try:
                before = source.stat()
                with source.open('rb') as reader, prepared.open('wb') as writer:
                    shutil.copyfileobj(reader, writer); writer.flush(); os.fsync(writer.fileno())
                after = source.stat()
                if (before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns):
                    raise ValueError('The source XML changed while loading. The previous library is safe; try scanning again.')
                library = legacy.Library.load(prepared, on_progress=lambda count,total: progress(job,count,count+5000,f'Read {count:,} songs from XML'))
            except Exception:
                prepared.unlink(missing_ok=True)
                raise
            progress(job, 1, 2, 'Indexing XML export')
        elif kind == 'live':
            result = run_com({'operation': 'scan'}, self.store.path, job, timeout=900, progress=lambda done,total,current: progress(job,done,total,current))
            expected = config.get('library_pid')
            if expected and result.get('library_pid') != expected:
                raise ValueError('iTunes is using a different library. Choose Current iTunes library to add it separately.')
            latest = self.profile(identity)['config']; latest['library_pid'] = result.get('library_pid', '')
            self.store.execute('UPDATE profiles SET config=? WHERE id=?', (encode(latest), identity))
            raw = {'Tracks': result['tracks'], 'Playlists': result['playlists']}
            library = legacy.Library(raw, legacy.Library.tracks_from_raw(raw['Tracks']), [legacy.Playlist(p) for p in raw['Playlists']])
        else:
            raw = {'Tracks': {}, 'Playlists': []}; count = 0; cached = {}
            old = self.store.rows('SELECT path,raw FROM tracks WHERE profile=?', (identity,))
            for row in old: cached[row['path']] = json.loads(row['raw'])
            roots = [checked_path(r, True) for r in config['roots']]
            errors = []
            for root in roots:
                def walk_error(exc): errors.append(str(exc))
                for folder, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
                    dirs[:] = [d for d in dirs if d not in config.get('exclusions', []) and not (Path(folder) / d).is_symlink() and not (hasattr(Path(folder) / d, 'is_junction') and (Path(folder) / d).is_junction())]
                    for filename in files:
                        path = Path(folder) / filename
                        if path.suffix.lower() not in AUDIO or path.is_symlink(): continue
                        checked_path(path, True)
                        count += 1; progress(job, count, count + 1, str(path))
                        stat = path.stat(); existing = cached.get(str(path), {})
                        if existing.get('_mtime') == stat.st_mtime_ns and existing.get('Size') == stat.st_size:
                            track = existing.copy()
                        else:
                            track = {'Name': path.stem, 'Location': path.as_uri(), 'Size': stat.st_size, '_mtime': stat.st_mtime_ns}
                            try:
                                info = metadata.inspect(path)
                                for field, values in info['tags'].items():
                                    if values: track[FIELDS[field][1]] = str(values[0])
                                track.update({'Total Time': int(info['duration'] * 1000), 'Bit Rate': int(info['bitrate'] / 1000), 'Sample Rate': info['sample_rate'], '_codec': info['codec']})
                            except Exception as exc: track['_error'] = str(exc)
                        track['Track ID'] = count
                        track.setdefault('Persistent ID', uuid.uuid5(uuid.NAMESPACE_URL, str(path)).hex[:16].upper())
                        raw['Tracks'][str(count)] = track
            if errors: raise ValueError('Scan incomplete; previous snapshot preserved. ' + '; '.join(errors[:5]))
            library = legacy.Library(raw, legacy.Library.tracks_from_raw(raw['Tracks']), [])
        previous = None
        snapshot = self.snapshot_path(identity)
        if snapshot.exists(): previous = self.library(identity, mutable=False)
        progress(job, 98, 100, 'Saving and indexing the library')
        try:
            rows = self.index_rows(identity, library)
            self.save_snapshot(identity, library, prepared_path=prepared); self.index(identity, library, rows)
        finally:
            if prepared: prepared.unlink(missing_ok=True)
        before = {t.raw.get('Persistent ID', str(i)): t.raw for i, t in (previous.tracks.items() if previous else [])}
        after = {t.raw.get('Persistent ID', str(i)): t.raw for i, t in library.tracks.items()}
        return {'tracks': len(after), 'added': len(after.keys() - before.keys()), 'removed': len(before.keys() - after.keys()), 'modified': sum(before[k] != after[k] for k in before.keys() & after.keys())}

    def tracks(self, identity, query='', offset=0, limit=100, missing=False):
        self.profile(identity)
        where = 'profile=?'
        args = [identity]
        if len(query) >= 3:
            where += ' AND id IN (SELECT id FROM track_text WHERE track_text MATCH ? AND profile=?)'
            args += ['"' + query.replace('"','""') + '"', identity]
        elif query:
            where += ' AND (name LIKE ? OR artist LIKE ? OR album LIKE ? OR genre LIKE ?)'
            args += [f'%{query}%'] * 4
        if missing: where += ' AND missing=1'
        count = self.store.rows(f'SELECT count(*) AS n FROM tracks WHERE {where}', args)[0]['n']
        rows = self.store.rows(f'SELECT * FROM tracks WHERE {where} ORDER BY artist,album,name LIMIT ? OFFSET ?', (*args, limit, offset))
        for r in rows: r['raw'] = json.loads(r['raw'])
        return {'total': count, 'items': rows}

    def overview(self, identity):
        scanned = self.profile(identity)['scanned']; version = self._index_versions[identity]
        cached = self._overviews.get(identity)
        if cached and cached[0] == (scanned,version): return cached[1]
        rows = self.store.rows('SELECT raw,path,missing FROM tracks WHERE profile=?', (identity,))
        raw = [json.loads(r['raw']) for r in rows]
        by_genre = Counter(t.get('Genre', 'Unspecified') or 'Unspecified' for t in raw)
        formats = Counter(Path(r['path']).suffix.lower() or 'Cloud / other' for r in rows)
        result = {'tracks': len(raw), 'artists': len({t.get('Artist') for t in raw if t.get('Artist')}), 'albums': len({(t.get('Artist'), t.get('Album')) for t in raw if t.get('Album')}), 'size': sum(int(t.get('Size', 0) or 0) for t in raw), 'unknown_sizes': sum(not t.get('Size') for t in raw), 'missing': sum(r['missing'] for r in rows), 'metadata_issues': sum(not t.get('Artist') or not t.get('Genre') or bool(t.get('_error')) for t in raw), 'genres': dict(by_genre.most_common(12)), 'formats': dict(formats), 'playlists': len(self.library(identity, mutable=False).playlists), 'last_scan': scanned}
        if version == self._index_versions[identity]: self._overviews[identity] = ((scanned,version), result)
        return result

    def save_preview(self, kind, identity, payload):
        preview = uuid.uuid4().hex
        if identity: payload['_snapshot_hash'] = digest(self.snapshot_path(identity))
        self.store.execute('INSERT INTO previews(id,kind,profile,payload,created) VALUES(?,?,?,?,?)', (preview, kind, identity, encode(payload), time.time()))
        return {'id': preview, 'kind': kind, 'profile': identity, **payload}

    def changes(self, identity, ids, fields, target, library=None):
        validate_fields(fields)
        if target not in ('live', 'file'): raise ValueError('Choose live iTunes or file tags.')
        library = library or self.library(identity); result = []
        for tid in ids:
            track = library.tracks.get(tid)
            if track is None: raise ValueError('Track not in library.')
            if track.raw.get('Protected') or 'protected' in str(track.raw.get('Kind', '')).lower():
                raise ValueError('Protected DRM media cannot be edited.')
            pid = track.raw.get('Persistent ID', '')
            if target == 'live':
                if self.profile(identity)['config']['kind'] == 'folder':
                    raise ValueError('Use a live iTunes scan or XML export with genuine persistent IDs for COM edits.')
                split_pid(pid)
            change = {'id': tid, 'pid': pid, 'name': track.name, 'fields': fields, 'expected': {k: track.raw.get(FIELDS[k][1], 0 if isinstance(v, int) else False if isinstance(v, bool) else '') for k, v in fields.items()}}
            if track.raw.get('_com_object_ids'): change['object_ids'] = track.raw['_com_object_ids']
            if target == 'file':
                path = legacy.file_uri_to_path(track.location or '')
                if not path: raise ValueError('Track has no editable local file.')
                change.update({'path': str(path), 'signature': signature(path)})
                metadata.inspect(path)
                if any(k not in metadata.TAGS for k in fields): raise ValueError('One or more selected fields require live iTunes editing.')
            result.append(change)
        return result

    def metadata_preview(self, identity, ids, fields, target):
        return self.save_preview('metadata', identity, {'changes': self.dedupe_changes(self.changes(identity, ids, fields, target), target), 'target': target})

    def dedupe_changes(self, changes, target):
        if target != 'file': return changes
        unique = {}
        for change in changes:
            key = change['path'].casefold()
            if key in unique and unique[key]['fields'] != change['fields']:
                raise ValueError('The same media file has conflicting proposed tags; edit it separately.')
            unique[key] = change
        return list(unique.values())

    def cleaner_preview(self, identity, options):
        library = self.library(identity); target = options.get('target', 'live'); changes = []; junk = []
        scope_names = options.get('scope_names', [])
        scope = {tid for p in library.playlists if p.name in scope_names for tid in p.track_ids()}
        lookup = legacy.online_lookup.OnlineLookup(prefer_lastfm=options.get('prefer_lastfm', False))
        for tid, track in library.tracks.items():
            if scope_names and ((tid not in scope) if options.get('scope_mode', 'include') == 'include' else (tid in scope)): continue
            old = str(track.raw.get('Genre', ''))
            if legacy.genre_rules.is_junk_track_name(track.name, str(track.location or '')):
                junk.append({'id': tid, 'name': track.name}); continue
            new = legacy.genre_rules.map_genre(legacy.genre_rules.strip_kids_genre(old))
            if options.get('unknown_lookup') and not old.strip(): new = lookup.lookup_genre_online(track.artist, track.name) or new
            if options.get('foreign_detect') and lookup.is_foreign_language(track.artist, track.name): new = 'International'
            if new and new != old:
                changes.extend(self.changes(identity, [tid], {'genre': new}, target, library))
        return self.save_preview('metadata', identity, {'changes': self.dedupe_changes(changes, target), 'target': target, 'junk_candidates': junk, 'note': 'Junk tracks are review candidates only. Quarantine local files separately; no live deletion is performed.'})

    def album_preview(self, identity, target='live', online=False):
        library = self.library(identity); tracks = []
        by_pid = {}
        for tid, t in library.tracks.items():
            r = t.raw; pid = r.get('Persistent ID', '')
            if not pid: continue
            def number(k):
                try: return int(str(r.get(k, 0)).split('/')[0])
                except ValueError: return 0
            tracks.append(legacy.album_merge.TrackInfo(pid, t.artist, r.get('Album Artist', ''), t.album, t.name, number('Track Number'), number('Track Count'), number('Disc Number'), number('Disc Count'), number('Year'), r.get('Genre', ''), bool(r.get('Compilation', False))))
            by_pid[pid] = tid
        groups = legacy.album_merge.find_split_groups(tracks)
        if online: groups = legacy.album_merge.confirm_split_groups_online(groups)
        reverse = {attr: key for key, (attr, _) in FIELDS.items()}
        changes = []
        for group in groups:
            for track, fields in legacy.album_merge.build_merge_plan(group):
                changes.extend(self.changes(identity, [by_pid[track.persistent_id]], {reverse[k]: v for k, v in fields.items()}, target, library))
        return self.save_preview('metadata', identity, {'target': target, 'changes': self.dedupe_changes(changes, target), 'album_groups': len(groups)})

    def duplicates(self, identity, mode='metadata'):
        library = self.library(identity)
        if mode == 'fingerprint':
            tool = shutil.which('fpcalc')
            if not tool: raise ValueError('Audio fingerprinting requires the official Chromaprint fpcalc tool installed on PATH. No fingerprints were simulated.')
            buckets = defaultdict(list); errors = []
            for track in library.tracks.values():
                path = legacy.file_uri_to_path(track.location or '')
                if not path or not path.is_file(): continue
                try:
                    result = subprocess.run([tool, '-json', str(checked_path(path, True))], capture_output=True, text=True, timeout=30, check=True)
                    fingerprint = json.loads(result.stdout)['fingerprint']
                    if fingerprint: buckets[fingerprint].append(track.track_id)
                except Exception as exc: errors.append(f'{track.name}: {exc}')
            if errors: self.store.audit('fingerprint_errors', {'errors': errors})
            return [{'ids': ids, 'canonical_id': max(ids, key=lambda i: library.tracks[i].completeness_score()), 'tier': 'exact_fingerprint', 'reason': 'Identical Chromaprint fingerprints; review before merging'} for ids in buckets.values() if len(ids) > 1]
        if mode == 'hash':
            buckets = defaultdict(list)
            for track in library.tracks.values():
                path = legacy.file_uri_to_path(track.location or '')
                if path and path.is_file(): buckets[path.stat().st_size].append(track)
            hashes = defaultdict(list)
            for tracks in buckets.values():
                if len(tracks) < 2: continue
                for track in tracks:
                    path = legacy.file_uri_to_path(track.location)
                    hashes[digest(path)].append(track.track_id)
            return [{'ids': ids, 'tier': 'exact_hash', 'reason': 'Identical SHA-256', 'canonical_id': max(ids, key=lambda i: (library.tracks[i].bitrate, library.tracks[i].completeness_score()))} for ids in hashes.values() if len(ids) > 1]
        settings = self.store.setting('preferences', {})
        groups = legacy.find_all_candidate_groups(library, low_confidence=settings.get('low_confidence', .80), high_confidence=settings.get('high_confidence', .92))
        plan = legacy.build_plan(library, groups)
        return [{'ids': [t.track_id for t in a.group_tracks], 'canonical_id': a.canonical_id, 'tier': str(a.tier), 'reason': a.canonical_reason, 'name': a.canonical_name, 'artist': a.canonical_artist, 'playlists': a.playlists_updated, 'warnings': a.smart_playlist_warnings, 'incomplete_album_overlap': a.incomplete_album_overlap, 'play_count': a.merged_play_count, 'rating': a.merged_rating} for a in plan.actions]

    def merge_preview(self, identity, groups, output):
        library = self.library(identity); selected = []; used = set()
        for group in groups:
            ids = group['ids']; canonical = group['canonical_id']
            if len(set(ids)) < 2 or canonical not in ids or any(i not in library.tracks or i in used for i in ids): raise ValueError('Invalid or overlapping duplicate selection.')
            used.update(ids)
            selected.append(legacy.manual_group([library.tracks[i] for i in ids], canonical))
        plan = legacy.build_plan(library, selected)
        path = checked_path(output)
        if path.exists(): raise ValueError('Choose a new XML output file; source cannot be overwritten.')
        return self.save_preview('merge', identity, {'groups': groups, 'output': str(path), 'summary': plan.summary_lines(), 'removed': plan.total_duplicates_removed, 'warning': 'Writes a separate XML export. Does not remove live tracks or physical media. Import/relink the export through a supported iTunes workflow.'})

    def transfer_preview(self, identity, ids, destination, mode='copy', template='{artist}/{album}/{track} - {title}'):
        if mode not in ('copy', 'move', 'quarantine'): raise ValueError('Invalid transfer mode.')
        root = checked_path(destination)
        library = self.library(identity); items = []; destinations = set(); sources = set()
        for tid in ids:
            if tid not in library.tracks: raise ValueError('Track not found.')
            track = library.tracks[tid]; source = legacy.file_uri_to_path(track.location or '')
            if not source: raise ValueError('Track has no local media file.')
            source = checked_path(source, True)
            if str(source).casefold() in sources: continue
            sources.add(str(source).casefold())
            if root == source.parent or root in source.parents or source.parent in root.parents:
                raise ValueError('Source and destination overlap; choose a separate destination.')
            values = {'artist': track.artist, 'album': track.album, 'album_artist': track.raw.get('Album Artist') or track.artist, 'year': track.raw.get('Year', ''), 'track': str(track.raw.get('Track Number', 0)).zfill(2), 'title': track.name, 'genre': track.raw.get('Genre', '')}
            relative = organized_path(template, values, source.suffix)
            if mode == 'quarantine': relative = Path(str(tid)) / source.name
            target = checked_path(root / relative)
            if not target.is_relative_to(root): raise ValueError('Destination escaped selected root.')
            if target.exists() or str(target).casefold() in destinations: raise ValueError(f'Filename collision: {target}')
            if target.parent.exists() and any(p.name.casefold() == target.name.casefold() for p in target.parent.iterdir()): raise ValueError('Case-insensitive filename collision.')
            destinations.add(str(target).casefold())
            items.append({'id': tid, 'source': str(source), 'destination': str(target), 'signature': signature(source)})
        ancestor = root
        while not ancestor.exists(): ancestor = ancestor.parent
        required = sum(i['signature']['size'] for i in items)
        if shutil.disk_usage(ancestor).free < required + 16 * 1024 * 1024:
            raise ValueError('Insufficient disk space for the complete operation.')
        return self.save_preview('transfer', identity, {'items': items, 'mode': mode, 'bytes': sum(i['signature']['size'] for i in items), 'warning': 'Moving or quarantining media can break live iTunes references. A relink XML is saved in application data; live references are not silently changed.'})

    def restore_preview(self, transfer):
        rows = self.store.rows("SELECT * FROM transfers WHERE id=? AND mode IN ('quarantine','move') AND status='complete'", (transfer,))
        if not rows: raise ValueError('Restorable manifest not found.')
        item = rows[0]
        if Path(item['source']).exists(): raise ValueError('Original path is occupied; restore will not overwrite it.')
        sig = signature(item['destination'])
        if sig['sha256'] != item['hash']: raise ValueError('Quarantine file was modified; manual review required.')
        return self.save_preview('transfer', None, {'mode': 'restore', 'items': [{'source': item['destination'], 'destination': item['source'], 'signature': sig}], 'bytes': sig['size']})

    def undo_preview(self, identity, job):
        jobs = self.store.rows('SELECT payload FROM jobs WHERE id=?', (job,))
        if jobs and json.loads(jobs[0]['payload']).get('profile') != identity: raise ValueError('Switch to the library used by the original job before undoing it.')
        edits = self.store.rows("SELECT * FROM edits WHERE job=? AND status IN ('applied','uncertain','pending') ORDER BY created DESC", (job,))
        if not edits: raise ValueError('No journaled metadata changes to undo.')
        if all(e['target'] != 'live' for e in edits):
            grouped = {}; library = self.library(identity)
            by_path = {str(legacy.file_uri_to_path(t.location or '')): t for t in library.tracks.values()}
            for e in edits:
                path = e['target']; track = by_path.get(path)
                if track is None: raise ValueError('The original media path is no longer in this profile; inspect the backup manually.')
                change = grouped.setdefault(path, {'id': track.track_id, 'pid': e['pid'], 'name': track.name, 'path': path, 'signature': signature(path), 'fields': {}, 'restore_values': {}, 'expected_tags': {}})
                old, new = json.loads(e['old']), json.loads(e['new'])
                change['fields'][e['field']] = old[0] if old else ''
                change['restore_values'][e['field']] = old
                change['expected_tags'][e['field']] = new
            return self.save_preview('metadata', identity, {'target': 'file', 'changes': list(grouped.values()), 'undo_of': job})
        changes = defaultdict(lambda: {'fields': {}, 'expected': {}})
        for e in edits:
            change = changes[e['pid']]; change['pid'] = e['pid']
            change['fields'][e['field']] = json.loads(e['old']); change['expected'][e['field']] = json.loads(e['new'])
        if not changes: raise ValueError('No live field changes to undo.')
        return self.save_preview('metadata', identity, {'target': 'live', 'changes': list(changes.values()), 'undo_of': job})

    def commit(self, preview):
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM previews WHERE id=?', (preview,)).fetchone()
            if not row or row['consumed']: raise ValueError('Preview not found or already committed.')
            if time.time() - row['created'] > 3600: raise ValueError('Preview expired; regenerate it.')
            payload = json.loads(row['payload'])
            if row['profile'] and digest(self.snapshot_path(row['profile'])) != payload['_snapshot_hash']: raise ValueError('Library changed since preview; regenerate it.')
            payload['profile'] = row['profile']
            job = uuid.uuid4().hex; now = time.time()
            db.execute('UPDATE previews SET consumed=1 WHERE id=?', (preview,))
            db.execute('INSERT INTO jobs(id,kind,payload,status,created,updated) VALUES(?,?,?,?,?,?)', (job, row['kind'], encode(payload), 'queued', now, now))
        self.jobs.wake.set(); return job

    def run_job(self, kind, payload, job, progress):
        identity = payload.get('profile')
        if kind == 'scan': return self.scan(identity, job, progress)
        if kind == 'metadata':
            library = self.library(identity); changes = payload['changes']; results = []; edited = {}
            by_pid = defaultdict(list); by_path = defaultdict(list)
            for track in library.tracks.values():
                by_pid[track.raw.get('Persistent ID', '')].append(track)
                by_path[str(legacy.file_uri_to_path(track.location or ''))].append(track)
            batch_size = 20 if payload['target'] == 'live' else 1
            try:
                for start in range(0, len(changes), batch_size):
                    batch = changes[start:start + batch_size]
                    progress(job, start, len(changes) + 1, batch[0].get('name', batch[0]['pid']))
                    if payload['target'] == 'live':
                        outcomes = run_com({'operation': 'edit', 'changes': batch, 'library_pid': self.profile(identity)['config'].get('library_pid')}, self.store.path, job, timeout=120)
                    else:
                        change = batch[0]
                        try: outcomes = [metadata.write_file(change, self.store, job, self.data_dir)]
                        except Exception as exc: outcomes = [{'pid': change['pid'], 'fields': {}, 'errors': [str(exc)]}]
                    for change, result in zip(batch, outcomes):
                        results.append(result)
                        targets = by_path[change.get('path', '')] if payload['target'] == 'file' else by_pid[change['pid']]
                        for track in targets:
                            for field, value in result['fields'].items(): track.raw[FIELDS[field][1]] = value
                            if result['fields']: edited[track.track_id] = track
                    progress(job, start + len(batch), len(changes) + 1, batch[-1].get('name', batch[-1]['pid']))
            finally:
                if edited:
                    self.store.execute("UPDATE jobs SET current='Saving verified changes' WHERE id=?", (job,))
                    self.save_snapshot(identity, library); self.index_changes(identity, edited.values())
            errors = sum(bool(r['errors']) for r in results)
            if errors: self.store.audit('partial_metadata', {'job': job, 'results': results})
            return {'results': results, 'failed_tracks': errors, 'partial': bool(errors)}
        if kind == 'merge':
            library = self.library(identity)
            groups = [legacy.manual_group([library.tracks[i] for i in g['ids']], g['canonical_id']) for g in payload['groups']]
            plan = legacy.build_plan(library, groups); legacy.apply_plan(library, plan)
            output = checked_path(payload['output'])
            self.export_xml(library, output)
            return {'output': str(output), 'removed': plan.total_duplicates_removed}
        if kind == 'playlist':
            library = self.library(identity)
            library.playlists.append(legacy.Playlist({'Name': payload['name'], 'Playlist Items': [{'Track ID': tid} for tid in payload['ids']]}))
            self.export_xml(library, Path(payload['output']))
            return {'output': payload['output'], 'unmatched': payload['unmatched']}
        if kind == 'relink':
            library = self.library(identity)
            for item in payload['items']:
                legacy.relink_track_location(library.tracks[item['id']], checked_path(item['path'], True))
            self.export_xml(library, Path(payload['output']))
            return {'output': payload['output'], 'relinked': len(payload['items'])}
        if kind == 'artwork':
            results = []
            for i, item in enumerate(payload['items']):
                progress(job, i, len(payload['items']), item['path'])
                path = checked_path(item['path'], True)
                if signature(path) != item['signature']: raise ValueError('Audio changed since artwork preview.')
                backup = self.data_dir / 'backups' / job / str(item['id']) / path.name
                backup.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, backup)
                if digest(backup) != item['signature']['sha256']: raise ValueError('Backup verification failed.')
                metadata.write_artwork(path, payload.get('image'), payload.get('remove', False))
                results.append({'id': item['id'], 'backup': str(backup)})
            return results
        if kind == 'transfer':
            manifests = []; start = payload.get('resume_from', 0); library = self.library(identity) if identity else None
            # A crash after final creation but before checkpoint must be inspected, never guessed past.
            for i, item in enumerate(payload['items']):
                if i < start: continue
                progress(job, i, len(payload['items']), item['source'])
                manifests.append(verified_transfer(item['source'], item['destination'], item['signature'], payload['mode'], self.store, job))
                if library and payload['mode'] == 'move':
                    legacy.relink_track_location(library.tracks[item['id']], Path(item['destination']))
                progress(job, i + 1, len(payload['items']), item['source'])
            output = None
            if library and payload['mode'] == 'move':
                output = self.data_dir / 'exports' / f'{job}-relinked.xml'
                self.export_xml(library, output)
            return {'manifests': manifests, 'relink_xml': str(output) if output else None}
        if kind == 'verify':
            library = self.library(identity); results = []
            for i, tid in enumerate(payload['ids']):
                progress(job, i, len(payload['ids']), str(tid))
                track = library.tracks[tid]; path = legacy.file_uri_to_path(track.location or '')
                try: results.append({'id': tid, **signature(path)})
                except Exception as exc: results.append({'id': tid, 'error': str(exc)})
            return results
        if kind == 'folder_health':
            root = checked_path(payload['root'], True)
            library = self.library(identity)
            known = {str(p.resolve()).casefold() for track in library.tracks.values() if (p := legacy.file_uri_to_path(track.location or ''))}
            orphaned = []; empty = []; invalid = []; count = 0; errors = []
            for folder, dirs, files in os.walk(root, followlinks=False, onerror=lambda exc: errors.append(str(exc))):
                dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink() and not (hasattr(Path(folder) / d, 'is_junction') and (Path(folder) / d).is_junction())]
                if not dirs and not files: empty.append(folder)
                for filename in files:
                    path = Path(folder) / filename
                    if path.is_symlink() or path.suffix.lower() not in AUDIO: continue
                    count += 1; progress(job, count, count + 1, str(path))
                    checked_path(path, True)
                    if str(path.resolve()).casefold() not in known: orphaned.append({'path': str(path), 'size': path.stat().st_size})
                    if safe_component(path.stem) != path.stem: invalid.append(str(path))
            naming = defaultdict(set)
            for track in library.tracks.values():
                for field in ('Artist', 'Album', 'Album Artist'):
                    value = str(track.raw.get(field, '')).strip()
                    if value: naming[(field, value.casefold())].add(value)
            return {'profile': identity, 'root': str(root), 'scanned_files': count, 'orphaned': orphaned, 'empty_folders': empty, 'invalid_names': invalid, 'inconsistent_names': [{'field': key[0], 'values': sorted(values)} for key, values in naming.items() if len(values) > 1], 'errors': errors, 'note': 'Orphans are candidates, not proof that files are unwanted. Empty directories and invalid names are reported only.'}
        raise ValueError('Unsupported job operation.')

    def export_xml(self, library, output):
        output = checked_path(output); output.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=output.parent, suffix='.xml'); os.close(fd)
        try:
            library.save(Path(temp)); legacy.Library.load(Path(temp))
            with open(output, 'xb') as dest, open(temp, 'rb') as source:
                shutil.copyfileobj(source, dest); dest.flush(); os.fsync(dest.fileno())
        finally: Path(temp).unlink(missing_ok=True)

    def playlists(self, identity):
        library = self.library(identity, mutable=False)
        from .artwork import encode_thumbnail, image_file
        covers = self.profile(identity)['config'].get('playlist_covers', {})
        result = []
        for i, playlist in enumerate(library.playlists):
            key = playlist.raw.get('Playlist Persistent ID') or f'{i}:{playlist.name}'
            image = image_file(covers[key]) if covers.get(key) else None
            if image is None:
                for field in ('Playlist Image', 'Artwork', 'Image'):
                    value = playlist.raw.get(field)
                    if isinstance(value, bytes): image = encode_thumbnail(value)
                    elif isinstance(value, str):
                        path = legacy.file_uri_to_path(value) if value.startswith('file:') else Path(value)
                        if path: image = image_file(path)
                    if image: break
            ids = playlist.track_ids()
            result.append({'index':i,'name':playlist.name,'image':image,'ids':ids,'broken':[tid for tid in ids if tid not in library.tracks],'duplicates':len(ids)-len(set(ids)),'smart':playlist.is_smart,'tracks':[{'id':tid,'name':library.tracks[tid].name,'artist':library.tracks[tid].artist} for tid in ids if tid in library.tracks]})
        return result

    def playlist_cover(self, identity, index, image):
        from .artwork import image_file
        library = self.library(identity, mutable=False)
        if not 0 <= index < len(library.playlists): raise ValueError('Playlist not found.')
        if image and not image_file(checked_path(image, True)): raise ValueError('Choose a readable image smaller than 20 MB.')
        playlist = library.playlists[index]
        key = playlist.raw.get('Playlist Persistent ID') or f'{index}:{playlist.name}'
        profile = self.profile(identity); covers = profile['config'].setdefault('playlist_covers', {})
        if image: covers[key] = image
        else: covers.pop(key, None)
        self.store.execute('UPDATE profiles SET config=? WHERE id=?',(encode(profile['config']),identity))
        return {'saved':True}

    def playlist_export(self, identity, index, output):
        library = self.library(identity); playlist = library.playlists[index]
        lines = ['#EXTM3U']
        for tid in playlist.track_ids():
            t = library.tracks.get(tid)
            if t:
                path = legacy.file_uri_to_path(t.location or '')
                if path:
                    lines += [f'#EXTINF:{int(t.total_time_ms / 1000)},{t.artist} - {t.name}'.replace('\n', ' ').replace('\r', ' '), str(path)]
        path = checked_path(output)
        with open(path, 'x', encoding='utf-8') as f: f.write('\n'.join(lines) + '\n')
        return {'output': str(path)}

    def playlist_import(self, identity, source, name):
        path = checked_path(source, True)
        if path.suffix.lower() not in ('.m3u', '.m3u8'): raise ValueError('Select M3U or M3U8.')
        library = self.library(identity); lookup = {}
        for tid, track in library.tracks.items():
            p = legacy.file_uri_to_path(track.location or '')
            if p: lookup[str(p.resolve()).casefold()] = tid
        ids = []; unmatched = []
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip() or line.startswith('#'): continue
            if '://' in line: unmatched.append(line); continue
            candidate = Path(line) if Path(line).is_absolute() else path.parent / line
            tid = lookup.get(str(candidate.resolve()).casefold())
            if tid is None: unmatched.append(line)
            else: ids.append(tid)
        return self.save_preview('playlist', identity, {'name': name, 'ids': ids, 'unmatched': unmatched, 'output': str(self.data_dir / 'exports' / f'{uuid.uuid4().hex}-playlist.xml')})

    def import_settings(self, path, kind):
        path = checked_path(path, True)
        if kind == 'cleaner':
            settings = json.loads(path.read_text(encoding='utf-8'))
            # Secrets stay in the old installation; import non-secret preferences only.
            settings = {k: v for k, v in settings.items() if not any(s in k.lower() for s in ('key', 'token', 'password', 'secret'))}
        elif kind == 'consolidator':
            uri = path.as_uri() + '?mode=ro'
            with closing(sqlite3.connect(uri, uri=True)) as db:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'settings' not in tables: raise ValueError('No legacy settings table.')
                settings = dict(db.execute('SELECT key,value FROM settings'))
        else: raise ValueError('Unknown legacy settings format.')
        old = self.store.setting('legacy_settings', {}); old[kind] = settings
        self.store.set_setting('legacy_settings', old)
        return {'imported': len(settings), 'preserved_unknown_settings': True}
