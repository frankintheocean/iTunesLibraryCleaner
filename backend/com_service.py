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


def find_track(app, pid, cache=None, name=None, object_ids=None):
    """Never match by title. A collection lookup can miss a valid live track."""
    high, low = split_pid(pid)
    collection = app.LibraryPlaylist.Tracks
    try: track = collection.ItemByPersistentID(high, low)
    except Exception: track = None
    if track is not None:
        # Verify identity whenever the client exposes the iTunes ID reader.
        if not hasattr(app, 'ITObjectPersistentIDHigh') or pid_for(app, track) == pid.upper():
            return track
    # Hints only narrow the read. Every candidate must have the exact stored ID.
    if object_ids:
        try:
            candidate = app.GetITObjectByID(*object_ids)
            if candidate is not None and pid_for(app, candidate) == pid.upper(): return candidate
        except Exception: pass
    if name:
        try:
            candidate = collection.ItemByName(name)
            if candidate is not None and pid_for(app, candidate) == pid.upper(): return candidate
        except Exception: pass
    cache = cache if cache is not None else {}
    if not cache.get('_loaded'):
        try: iterator = iter(collection)
        except TypeError: iterator = (collection.Item(i) for i in range(1, collection.Count + 1))
        for track in iterator:
            cache[pid_for(app, track)] = track
        cache['_loaded'] = True
    if pid.upper() in cache: return cache[pid.upper()]
    raise ValueError('This track ID is not in the currently open iTunes library. Check that iTunes has the right library open, then rescan it.')


def write_tracks(app_factory, changes, store, job):
    """Journal before each write. Do not pretend a batch of COM properties is atomic."""
    app = app_factory()
    results = []; lookup = {}
    for change in changes:
        pid, fields = change['pid'], change['fields']
        validate_fields(fields)
        high, low = split_pid(pid)
        item = {'pid': pid, 'fields': {}, 'errors': []}
        try:
            track = find_track(app, pid, lookup, change.get('name'), change.get('object_ids'))
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
                        track = find_track(app, pid, name=change.get('name'), object_ids=change.get('object_ids'))
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



def connect_itunes(client=None):
    """Attach through the ROT; use classic COM activation when it is not registered there.

    Apple's desktop installer can expose iTunes.Application through Dispatch while
    GetActiveObject returns MK_E_UNAVAILABLE. Activation may open classic iTunes.
    Other COM failures remain explicit instead of silently changing connection paths.
    Call only inside the caller's initialized COM apartment.
    """
    if client is None:
        import win32com.client
        client = win32com.client
    for attempt in range(3):
        try:
            try: return client.GetActiveObject('iTunes.Application')
            except Exception as exc:
                if getattr(exc, 'hresult', None) != -2147221021: raise
                return client.Dispatch('iTunes.Application')
        except Exception as exc:
            if attempt == 2 or getattr(exc, 'hresult', None) not in (-2147418111, -2147417846, -2147417848, -2147023174): raise
            time.sleep(.1 * (attempt + 1))


def scan_library(app, progress=None):
    """Read tracks and playlists through the documented IITPlaylist.Source member."""
    library_pid = pid_for(app, app.LibraryPlaylist)
    result = {'tracks': {}, 'playlists': [], 'library_pid': library_pid}
    tracks = app.LibraryPlaylist.Tracks
    count = tracks.Count
    playlists = list(app.LibraryPlaylist.Source.Playlists)
    def collection_count(collection):
        try: return collection.Count
        except AttributeError: return len(collection)
    total = count + sum(collection_count(p.Tracks) for p in playlists) + 1
    if progress: progress(0, total, 'Reading the open iTunes library')
    database_ids = {}
    try: iterator = iter(tracks)
    except TypeError: iterator = (tracks.Item(i) for i in range(1, count + 1))
    for i, track in enumerate(iterator, 1):
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
        database_id = optional_property(track, 'TrackDatabaseID')
        if isinstance(database_id, int) and database_id > 0: database_ids[database_id] = i
        if progress and (i % 100 == 0 or i == count):
            progress(i, total, f'Reading iTunes songs: {i:,} of {count:,}')
    pid_map = {v['Persistent ID']: v['Track ID'] for v in result['tracks'].values()}
    done = count
    for playlist in playlists:
        items = []
        for track in playlist.Tracks:
            database_id = optional_property(track, 'TrackDatabaseID')
            identity = database_ids.get(database_id)
            if identity is None: identity = pid_map.get(pid_for(app, track))
            if identity is not None: items.append({'Track ID': identity})
            done += 1
            if progress and done % 200 == 0: progress(done, total, f'Reading playlist: {playlist.Name}')
        result['playlists'].append({'Name': playlist.Name, 'Playlist Persistent ID': pid_for(app, playlist), 'Playlist Items': items})
    if pid_for(app, app.LibraryPlaylist) != library_pid or tracks.Count != count or len(result['tracks']) != count:
        raise ValueError('The open iTunes library changed during the scan. Its previous saved copy is safe; scan again.')
    return result


def read_live_artwork(app, pid, name=None):
    """Read a cover in the owning COM apartment without editing its track."""
    import tempfile
    from .artwork import encode_thumbnail
    track = find_track(app, pid, name=name)
    if not track.Artwork.Count: return None
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / 'cover.png'
        track.Artwork.Item(1).SaveArtworkToFile(str(target))
        return encode_thumbnail(target.read_bytes())



def find_playlist(app, playlist_pid):
    if not re.fullmatch(r'[0-9a-fA-F]{16}', playlist_pid or ''):
        raise ValueError('Playlist edits require a valid 16-digit playlist persistent ID.')
    source=app.LibraryPlaylist.Source
    try: playlists=list(source.Playlists)
    except TypeError: playlists=[source.Playlists.Item(i) for i in range(1,source.Playlists.Count+1)]
    for playlist in playlists:
        try:
            if pid_for(app,playlist).upper()==playlist_pid.upper():return playlist
        except Exception:continue
    raise ValueError('That playlist is no longer in the currently open iTunes library. Rescan and retry.')


def _require_library(app, expected_library):
    if expected_library and pid_for(app,app.LibraryPlaylist).upper()!=expected_library.upper():
        raise ValueError('iTunes is using a different library. Reopen the library used for this preview.')


def _wait_add(status, deadline_seconds=180):
    if status is None:raise RuntimeError('iTunes did not accept the requested file operation.')
    deadline=time.monotonic()+deadline_seconds
    while bool(getattr(status,'InProgress',False)):
        if time.monotonic()>=deadline:raise TimeoutError('iTunes has not finished importing the file yet. Check iTunes before retrying.')
        time.sleep(.25)
    return True


def perform_library_operation(app,payload):
    operation=payload['operation'];_require_library(app,payload.get('library_pid'))
    if operation=='delete_tracks':
        results=[];cache={}
        for item in payload.get('tracks',[]):
            track=find_track(app,item['pid'],cache,item.get('name'));track.Delete()
            results.append({'pid':item['pid'],'deleted_from_itunes':True})
        return results
    if operation=='add_file':
        _wait_add(app.LibraryPlaylist.AddFile(payload['path']))
        return {'added':payload['path']}
    if operation=='playlist_cover':
        playlist=find_playlist(app,payload['playlist_pid'])
        setter=getattr(playlist,'AddArtworkFromFile',None)
        if callable(setter):setter(payload['image']);return {'applied':True}
        artwork=getattr(playlist,'Artwork',None)
        add=getattr(artwork,'AddArtworkFromFile',None) if artwork is not None else None
        if callable(add):add(payload['image']);return {'applied':True}
        raise RuntimeError('This classic iTunes COM interface does not expose playlist artwork editing. The picture is saved in iTunes Manager; no song artwork was changed.')
    if operation=='playlist_order':
        playlist=find_playlist(app,payload['playlist_pid'])
        if bool(getattr(playlist,'Smart',False)):raise ValueError('Smart playlists are managed by their rules and cannot be manually reordered.')
        ordered=[str(v).upper() for v in payload.get('ids',[])]
        original_tracks=list(playlist.Tracks)
        original=[pid_for(app,t).upper() for t in original_tracks]
        if len(set(original))!=len(original) or len(set(ordered))!=len(ordered):raise ValueError('This playlist has repeated tracks. iTunes COM cannot safely reorder repeated entries by persistent ID.')
        if len(ordered)!=len(original) or sorted(ordered)!=sorted(original):raise ValueError('Playlist contents changed since review; rescan and reorder again.')
        # Only use an explicit playlist-only move API if this iTunes build exposes one.
        # IITTrack.Delete removes the track itself, so never delete/re-add tracks to simulate a reorder.
        track_by_pid={pid:track for pid,track in zip(original,original_tracks)}
        move_track=getattr(playlist,'MoveTrack',None)
        move_to_order=getattr(playlist,'MoveTrackToPosition',None)
        if callable(move_track) or callable(move_to_order):
            try:
                for position,pid in enumerate(ordered,1):
                    track=track_by_pid[pid]
                    if callable(move_track):move_track(track,position)
                    else:move_to_order(track,position)
                actual=[pid_for(app,t).upper() for t in list(playlist.Tracks)]
                if actual!=ordered:raise RuntimeError('iTunes did not retain the requested order when it was read back.')
                return {'reordered':len(ordered),'verified':True}
            except Exception as exc:
                raise RuntimeError(f'Live playlist reorder was not verified. No track objects were deleted: {exc}') from exc
        raise RuntimeError('This version of classic iTunes does not expose a safe playlist-only reorder method through COM. No songs or playlist entries were deleted. Change the order in iTunes itself or use a version that exposes a move method.')
    raise ValueError('Unsupported live-library operation.')


def _perform(payload, database, job, pipe):
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            factory = lambda: connect_itunes(win32com.client)
            app = factory()
            operation = payload['operation']
            if operation == 'status':
                for attempt in range(3):
                    try:
                        result = {'available': True, 'version': app.Version, 'tracks': app.LibraryPlaylist.Tracks.Count, 'library_name': app.LibraryPlaylist.Name, 'library_pid': pid_for(app, app.LibraryPlaylist), 'xml_path': str(optional_property(app, 'LibraryXMLPath'))}
                        break
                    except Exception as exc:
                        if attempt == 2 or getattr(exc, 'hresult', None) not in (-2147418111, -2147417846, -2147417848, -2147023174): raise
                        time.sleep(.2 * (attempt + 1)); app = factory()
            elif operation == 'artwork':
                result = {'image': read_live_artwork(app, payload['pid'], payload.get('name'))}
            elif operation == 'scan':
                result = scan_library(app, lambda done,total,current: pipe.send({'progress': [done,total,current]}))
            elif operation in ('playlist_cover','playlist_order','delete_tracks','add_file'):
                result = perform_library_operation(app, payload)
            elif operation == 'edit':
                expected_library = payload.get('library_pid')
                if expected_library:
                    def factory():
                        current = connect_itunes(win32com.client)
                        if pid_for(current, current.LibraryPlaylist) != expected_library:
                            raise ValueError('iTunes is using a different library. Reopen the library used for this preview.')
                        return current
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


def run_com(payload, database, job='', timeout=30, progress=None, max_timeout=6 * 60 * 60):
    if sys.platform != 'win32':
        raise RuntimeError('Live iTunes requires Windows, classic iTunes running, and pywin32. Apple Music for Windows does not expose this COM interface.')
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_perform, args=(payload, str(database), job, child))
    process.start()
    child.close()
    try:
        scanning = payload.get('operation') == 'scan'
        started = time.monotonic()
        deadline = started + timeout
        hard_deadline = started + (max_timeout if scanning else timeout)
        last_done = -1
        last_progress = (0, 1, 'Waiting for iTunes') if scanning else None
        check_at = started + 2
        while True:
            now = time.monotonic()
            remaining = min(deadline, hard_deadline) - now
            if remaining <= 0:
                if scanning:
                    raise TimeoutError('The read-only iTunes scan stopped responding or reached its time limit. No live metadata was changed. Your previous saved library is safe; check iTunes for an open dialog, then retry the scan.')
                if payload.get('operation') == 'edit':
                    raise TimeoutError('iTunes did not respond before the timeout. Any pending writes have an uncertain outcome; inspect field history before retrying.')
                raise TimeoutError('iTunes did not respond in time. Check iTunes for an open dialog, then refresh the connection.')
            if not parent.poll(min(.5, remaining)):
                # Keep cancel, shutdown and pause controls responsive during slow reads.
                if scanning and progress and last_progress and now >= check_at:
                    before = time.monotonic()
                    progress(*last_progress)
                    deadline += time.monotonic() - before
                    check_at = time.monotonic() + 2
                continue
            try: response = parent.recv()
            except EOFError as exc:
                if scanning:
                    raise RuntimeError('The read-only iTunes scan stopped unexpectedly. No live metadata was changed; your previous saved library is safe.') from exc
                raise RuntimeError('The iTunes worker stopped unexpectedly. Check field records before retrying a write.') from exc
            if 'progress' in response:
                values = response['progress']
                if progress: progress(*values)
                last_progress = values
                # A large healthy scan can take longer than fifteen minutes.
                # Only real forward progress extends the idle window.
                if scanning and values[0] > last_done:
                    last_done = values[0]
                    deadline = time.monotonic() + timeout
                continue
            if 'error' in response: raise RuntimeError(response['error'])
            return response['result']
    finally:
        process.join(.5)
        if process.is_alive(): process.terminate()
        process.join(5)
        parent.close()
