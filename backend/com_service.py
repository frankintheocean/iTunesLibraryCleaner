"""Live iTunes integration. COM objects never leave their owning process/apartment."""
from __future__ import annotations
import multiprocessing
import re
import sys
import time
from pathlib import Path
from .store import Store

FIELDS = {
    'name': ('Name', 'Name'), 'artist': ('Artist', 'Artist'),
    'album': ('Album', 'Album'), 'album_artist': ('AlbumArtist', 'Album Artist'),
    'genre': ('Genre', 'Genre'), 'year': ('Year', 'Year'),
    'track': ('TrackNumber', 'Track Number'), 'track_count': ('TrackCount', 'Track Count'),
    'disc': ('DiscNumber', 'Disc Number'), 'disc_count': ('DiscCount', 'Disc Count'),
    'composer': ('Composer', 'Composer'), 'comment': ('Comment', 'Comments'),
    'compilation': ('Compilation', 'Compilation'), 'rating': ('Rating', 'Rating'),
}
NUMERIC = {'year', 'track', 'track_count', 'disc', 'disc_count', 'rating'}


def validate_fields(fields):
    if not fields or any(k not in FIELDS for k in fields):
        raise ValueError('Choose supported writable metadata fields.')
    for key, value in fields.items():
        if key in NUMERIC:
            maximum = 100 if key == 'rating' else 9999
            if type(value) is not int or not 0 <= value <= maximum:
                raise ValueError(f'{key} must be an integer from 0 to {maximum}.')
        elif key == 'compilation':
            if type(value) is not bool:
                raise ValueError('Compilation must be true or false.')
        elif not isinstance(value, str) or len(value) > 4096 or '\x00' in value:
            raise ValueError(f'Invalid {key}.')


def split_pid(pid):
    if not re.fullmatch(r'[0-9a-fA-F]{16}', pid or ''):
        raise ValueError('Live edits require a valid 16-digit persistent ID.')
    halves = [int(pid[:8], 16), int(pid[8:], 16)]
    return tuple(n - 2**32 if n >= 2**31 else n for n in halves)


def pid_for(app, track):
    return f'{app.ITObjectPersistentIDHigh(track) & 0xffffffff:08X}{app.ITObjectPersistentIDLow(track) & 0xffffffff:08X}'


def optional_property(track, name):
    try: return getattr(track, name)
    except Exception: return ''


def write_tracks(app_factory, changes, store, job):
    """Journal before each write. Do not pretend a batch of COM properties is atomic."""
    app = app_factory()
    results = []
    for change in changes:
        pid, fields = change['pid'], change['fields']
        validate_fields(fields)
        high, low = split_pid(pid)
        item = {'pid': pid, 'fields': {}, 'errors': []}
        try:
            track = app.LibraryPlaylist.Tracks.ItemByPersistentID(high, low)
            if track is None:
                raise ValueError('Track no longer exists in live iTunes.')
            kind = str(optional_property(track, 'KindAsString'))
            location = str(optional_property(track, 'Location'))
            if 'protected' in kind.lower() or location.lower().endswith('.m4p'):
                raise ValueError('Protected DRM media is read-only in this application.')
            for field, value in fields.items():
                attr = FIELDS[field][0]
                old = getattr(track, attr)
                expected = change.get('expected', {}).get(field, old)
                if old != expected:
                    item['errors'].append(f'{field}: changed since preview; skipped.')
                    continue
                if old == value:
                    item['fields'][field] = value
                    continue
                identity = store.journal(job, pid, 'live', field, old, value)
                try:
                    try:
                        setattr(track, attr, value)
                    except Exception as exc:
                        # Reconnect only for rejected/busy calls, never retry an ambiguous write.
                        if getattr(exc, 'hresult', None) not in (-2147418111, -2147417846):
                            raise
                        time.sleep(.3)
                        app = app_factory()
                        track = app.LibraryPlaylist.Tracks.ItemByPersistentID(high, low)
                        current = getattr(track, attr)
                        if current == old:
                            setattr(track, attr, value)
                        elif current != value:
                            raise ValueError('Concurrent change during reconnect.')
                    if getattr(track, attr) != value:
                        raise ValueError('iTunes did not retain the requested value.')
                    store.finish_edit(identity, 'applied')
                    item['fields'][field] = value
                except Exception as exc:
                    store.finish_edit(identity, 'uncertain', str(exc))
                    item['errors'].append(f'{field}: {exc}')
        except Exception as exc:
            item['errors'].append(str(exc))
        results.append(item)
    return results


def scan_library(app):
    """Read tracks and playlists through the documented IITPlaylist.Source member."""
    result = {'tracks': {}, 'playlists': []}
    tracks = app.LibraryPlaylist.Tracks
    for i in range(1, tracks.Count + 1):
        track = tracks.Item(i)
        raw = {'Track ID': i, 'Persistent ID': pid_for(app, track)}
        for _, (attr, xml) in FIELDS.items():
            try:
                raw[xml] = getattr(track, attr)
            except Exception:
                pass
        for attr, xml in [('Location', 'Location'), ('Duration', 'Total Time'), ('BitRate', 'Bit Rate'), ('PlayedCount', 'Play Count'), ('Size', 'Size')]:
            try:
                value = getattr(track, attr)
                if attr == 'Location' and value:
                    value = Path(value).as_uri()
                if attr == 'Duration': value *= 1000
                raw[xml] = value
            except Exception:
                pass
        result['tracks'][str(i)] = raw
    pid_map = {v['Persistent ID']: v['Track ID'] for v in result['tracks'].values()}
    for playlist in app.LibraryPlaylist.Source.Playlists:
        items = []
        for track in playlist.Tracks:
            identity = pid_map.get(pid_for(app, track))
            if identity is not None: items.append({'Track ID': identity})
        result['playlists'].append({'Name': playlist.Name, 'Playlist Items': items})
    return result


def _perform(payload, database, job, pipe):
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            factory = lambda: win32com.client.GetActiveObject('iTunes.Application')
            app = factory()
            operation = payload['operation']
            if operation == 'status':
                result = {'available': True, 'version': app.Version, 'tracks': app.LibraryPlaylist.Tracks.Count}
            elif operation == 'scan':
                result = scan_library(app)
            elif operation == 'edit':
                # Store initializer must not reset running jobs in the isolated worker.
                store = Store.__new__(Store)
                store.path = Path(database)
                result = write_tracks(factory, payload['changes'], store, job)
            else:
                raise ValueError('Unsupported COM operation.')
            pipe.send({'result': result})
        finally:
            pythoncom.CoUninitialize()
    except Exception as exc:
        pipe.send({'error': str(exc)})
    finally:
        pipe.close()


def run_com(payload, database, job='', timeout=30):
    if sys.platform != 'win32':
        raise RuntimeError('Live iTunes requires Windows, classic iTunes running, and pywin32. Apple Music for Windows does not expose this COM interface.')
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_perform, args=(payload, str(database), job, child))
    process.start()
    child.close()
    try:
        if not parent.poll(timeout):
            raise TimeoutError('iTunes did not respond before the timeout. Any pending writes have an uncertain outcome; inspect field history before retrying.')
        response = parent.recv()
        if 'error' in response: raise RuntimeError(response['error'])
        return response['result']
    finally:
        process.join(.5)
        if process.is_alive(): process.terminate()
        process.join(5)
        parent.close()
