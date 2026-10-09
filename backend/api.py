from __future__ import annotations
import hmac
import base64
import hashlib
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ConfigDict
from .service import Service
from . import legacy, metadata
from .com_service import run_com, FIELDS
from .filesystem import AUDIO, checked_path, signature


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class LastFMConnect(Model):
    api_key: str = Field(min_length=32, max_length=32)
    username: str = Field(min_length=1, max_length=128)


class LastFMImage(Model):
    url: str = Field(max_length=2048)


class LastFMPicture(Model):
    kind: Literal['profile', 'track', 'album', 'artist']
    name: str = Field(min_length=1, max_length=512)
    artist: str = Field(default='', max_length=512)
    url: str = Field(default='', max_length=2048)


class LastFMTrackImage(Model):
    name: str = Field(min_length=1, max_length=512)
    artist: str = Field(min_length=1, max_length=512)


class DiscoveryLocation(Model):
    path: str = Field(min_length=1, max_length=4096)


class Profile(Model):
    name: str = Field(min_length=1, max_length=200)
    source: str = ''
    kind: Literal['xml', 'folder', 'live'] = 'xml'
    roots: list[str] = Field(default_factory=list)
    library_pid: str = Field(default='', pattern=r'^([0-9A-Fa-f]{16})?$')


class Selection(Model):
    profile: str
    ids: list[int] = Field(min_length=1, max_length=100000)


class Edit(Selection):
    target: Literal['live', 'file'] = 'live'
    fields: dict


class Cleaner(Model):
    profile: str
    target: Literal['live', 'file'] = 'live'
    unknown_lookup: bool = False
    foreign_detect: bool = False
    prefer_lastfm: bool = False
    scope_names: list[str] = Field(default_factory=list)
    scope_mode: Literal['include', 'exclude'] = 'include'


class Album(Model):
    profile: str
    target: Literal['live', 'file'] = 'live'
    online: bool = False


class Merge(Model):
    profile: str
    groups: list[dict] = Field(min_length=1)
    output: str


class Transfer(Selection):
    destination: str
    mode: Literal['copy', 'move', 'quarantine'] = 'copy'
    template: str = '{artist}/{album}/{track} - {title}'


class Confirm(Model):
    preview: str
    confirmed: Literal[True]


class ConfirmRemoval(Model):
    confirmed: Literal[True]


class Control(Model):
    action: Literal['pause', 'resume', 'cancel', 'retry', 'up', 'down']


class Undo(Model):
    profile: str
    job: str


class PathRequest(Model):
    path: str


class PlaylistExport(Model):
    profile: str
    index: int = Field(ge=0)
    output: str


class PlaylistImport(Model):
    profile: str
    source: str
    name: str = Field(min_length=1)


class PlaylistCover(Model):
    index: int = Field(ge=0)
    image: str = ''


class Relink(Model):
    profile: str
    root: str
    output: str


class Artwork(Selection):
    image: str = ''
    remove: bool = False


class SettingsImport(PathRequest):
    kind: Literal['cleaner', 'consolidator']


class Rules(Model):
    rules: list[dict] | None = None
    csv: str | None = None


class ProfileOptions(Model):
    roots: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    scan_interval_minutes: int = Field(default=0, ge=0, le=10080)
    destination: str = ''
    template: str = '{artist}/{album}/{track} - {title}'


class FolderHealth(Model):
    profile: str
    root: str


class Quarantine(Model):
    profile: str
    paths: list[str] = Field(min_length=1)
    destination: str


class RuleTest(Model):
    genre: str
    pattern: str = ''
    target: str = ''


def create_app(data_dir, token, ready=None):
    if len(token) < 32: raise ValueError('A secure session token is required.')
    service = Service(data_dir)

    @asynccontextmanager
    async def lifespan(app):
        if ready: ready()
        yield
        service.jobs.close()

    def auth(authorization: str = Header(default='')):
        if not hmac.compare_digest(authorization, 'Bearer ' + token): raise HTTPException(401, 'Unauthorized')

    app = FastAPI(title='iTunes Manager', version='3.1.1', dependencies=[Depends(auth)], lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path == '/lastfm/connect':
            return Response(json.dumps({'detail': 'Enter a valid Last.fm API key and username.'}), status_code=422, media_type='application/json')
        from fastapi.exception_handlers import request_validation_exception_handler
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return Response(json.dumps({'detail': str(exc)}), status_code=400, media_type='application/json')

    @app.exception_handler(OSError)
    async def os_error(request, exc):
        return Response(json.dumps({'detail': str(exc)}), status_code=400, media_type='application/json')

    @app.exception_handler(RuntimeError)
    async def runtime_error(request, exc):
        return Response(json.dumps({'detail': str(exc)}), status_code=503, media_type='application/json')

    @app.get('/health')
    def health(): return {'ready': True, 'version': '3.1.1'}

    @app.get('/discovery')
    def discover():
        paths = legacy.default_library_xml_candidates()
        default = service.store.setting('preferences', {}).get('default_xml_path', '').strip()
        if default:
            paths = [Path(default)] + [p for p in paths if str(p) != default]
        hidden = service.store.setting('discovery_hidden', [])
        paths = [p for p in paths if str(p) not in hidden]
        music = Path.home() / 'Music'
        return {'xml': [{'path': str(p), 'exists': p.exists()} for p in paths], 'databases': [{'path': str(music / 'iTunes' / 'iTunes Library.itl'), 'editable': False}], 'live_note': 'Classic iTunes on Windows only. Apple Music proprietary databases are read-only/unsupported; export XML or scan media.'}

    @app.post('/discovery/remove')
    def remove_discovery(body: DiscoveryLocation):
        hidden = service.store.setting('discovery_hidden', [])
        if body.path not in hidden: hidden.append(body.path)
        service.store.set_setting('discovery_hidden', hidden)
        return {'removed': True, 'note': 'Only this suggestion was hidden. Files and loaded libraries are unchanged.'}

    @app.post('/discovery/restore')
    def restore_discovery():
        service.store.set_setting('discovery_hidden', [])
        return {'restored': True}

    @app.get('/lastfm/status')
    def lastfm_status(): return service.lastfm.status()

    @app.post('/lastfm/connect')
    def lastfm_connect(body: LastFMConnect): return service.lastfm.connect(body.api_key, body.username)

    @app.post('/lastfm/disconnect')
    def lastfm_disconnect(): return service.lastfm.disconnect()

    @app.get('/lastfm/charts')
    def lastfm_charts(view: Literal['recent', 'tracks', 'artists', 'albums'] = 'recent',
                      period: Literal['overall', '7day', '1month', '3month', '6month', '12month'] = 'overall',
                      page: int = Query(1, ge=1, le=10000), refresh: bool = False):
        return service.lastfm.charts(view, period, page, refresh)

    @app.post('/lastfm/image')
    def lastfm_image(body: LastFMImage): return service.lastfm.image(body.url)

    @app.post('/lastfm/picture')
    def lastfm_picture(body: LastFMPicture): return service.lastfm.resolve_picture(body.kind, body.name, body.artist, body.url)

    @app.post('/lastfm/track-image')
    def lastfm_track_image(body: LastFMTrackImage): return service.lastfm.track_image(body.name, body.artist)

    @app.get('/com/status')
    def com_status():
        try: return run_com({'operation': 'status'}, service.store.path, timeout=15)
        except Exception as exc: return {'available': False, 'reason': str(exc)}

    @app.get('/profiles')
    def profiles(): return [p for row in service.store.rows('SELECT id FROM profiles ORDER BY name') if not (p := service.profile(row['id']))['config'].get('removed')]

    @app.post('/profiles/{identity}/remove')
    def remove_profile(identity: str, body: ConfirmRemoval):
        return service.remove_profile(identity)

    @app.post('/profiles')
    def profile(body: Profile):
        identity = service.add_profile(body.name, body.source, body.kind, body.roots)
        if body.kind == 'live' and body.library_pid:
            conf = service.profile(identity)['config']; conf['library_pid'] = body.library_pid.upper()
            service.store.execute('UPDATE profiles SET config=? WHERE id=?', (json.dumps(conf), identity))
        return {'id': identity, 'job': service.jobs.enqueue('scan', {'profile': identity})}

    @app.post('/profiles/{identity}/scan')
    def scan(identity: str):
        service.profile(identity)
        return {'job': service.jobs.enqueue('scan', {'profile': identity})}

    @app.post('/profiles/{identity}/options')
    def profile_options(identity: str, body: ProfileOptions):
        profile = service.profile(identity)
        for root in body.roots: checked_path(root, True)
        profile['config'].update(body.model_dump())
        service.store.execute('UPDATE profiles SET config=? WHERE id=?', (json.dumps(profile['config']), identity))
        return service.profile(identity)

    @app.get('/profiles/{identity}/tracks')
    def tracks(identity: str, q: str = '', offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), missing: bool = False):
        return service.tracks(identity, q, offset, limit, missing)

    @app.get('/profiles/{identity}/artwork/{track}')
    def track_artwork(identity: str, track: int):
        rows = service.store.rows('SELECT path,pid,name FROM tracks WHERE profile=? AND id=?', (identity, track))
        if not rows: raise ValueError('Track not found.')
        from .artwork import thumbnail
        row = rows[0]
        image = thumbnail(row['path'])
        if not image and service.profile(identity)['config']['kind'] == 'live':
            try:
                image = run_com({'operation': 'artwork', 'pid': row['pid'], 'name':row['name']}, service.store.path, timeout=5).get('image')
            except Exception:
                pass  # A missing cover must not stop browsing or editing.
        return {'image': image}

    @app.get('/profiles/{identity}/overview')
    def overview(identity: str): return service.overview(identity)

    @app.get('/profiles/{identity}/duplicates')
    def duplicates(identity: str, mode: Literal['metadata', 'hash', 'fingerprint'] = 'metadata'): return service.duplicates(identity, mode)

    @app.get('/profiles/{identity}/playlists')
    def playlists(identity: str): return service.playlists(identity)

    @app.post('/profiles/{identity}/playlist-cover')
    def playlist_cover(identity: str, body: PlaylistCover):
        return service.playlist_cover(identity, body.index, body.image)

    @app.post('/preview/metadata')
    def edit(body: Edit): return service.metadata_preview(body.profile, body.ids, body.fields, body.target)

    @app.post('/preview/cleaner')
    def cleaner(body: Cleaner): return service.cleaner_preview(body.profile, body.model_dump())

    @app.post('/preview/albums')
    def albums(body: Album): return service.album_preview(body.profile, body.target, body.online)

    @app.post('/preview/merge')
    def merge(body: Merge): return service.merge_preview(body.profile, body.groups, body.output)

    @app.post('/preview/transfer')
    def transfer(body: Transfer): return service.transfer_preview(body.profile, body.ids, body.destination, body.mode, body.template)

    @app.post('/folder-health')
    def folder_health(body: FolderHealth):
        service.profile(body.profile); checked_path(body.root, True)
        return {'job': service.jobs.enqueue('folder_health', body.model_dump())}

    @app.post('/preview/quarantine')
    def quarantine(body: Quarantine):
        root = checked_path(body.destination); items = []
        for value in dict.fromkeys(body.paths):
            source = checked_path(value, True)
            if source.suffix.lower() not in AUDIO: raise ValueError('Choose supported local media files.')
            if root in source.parents or source.parent in root.parents: raise ValueError('Source and quarantine overlap.')
            target = root / hashlib.sha256(str(source).encode()).hexdigest()[:16] / source.name
            if target.exists(): raise ValueError('Quarantine destination occupied.')
            items.append({'source': str(source), 'destination': str(target), 'signature': signature(source)})
        return service.save_preview('transfer', body.profile, {'items': items, 'mode': 'quarantine', 'bytes': sum(i['signature']['size'] for i in items), 'warning': 'Selected media will be moved to quarantine after hash verification. Restore through History. Review candidates before confirming.'})

    @app.post('/preview/restore/{identity}')
    def restore(identity: str): return service.restore_preview(identity)

    @app.post('/preview/undo')
    def undo(body: Undo): return service.undo_preview(body.profile, body.job)

    @app.post('/preview/relink')
    def relink(body: Relink):
        library = service.library(body.profile)
        matches = legacy.find_missing_files_in_root(library, checked_path(body.root, True))
        items = [{'id': m.track_id, 'path': str(m.found_path)} for m in matches]
        return service.save_preview('relink', body.profile, {'items': items, 'output': str(checked_path(body.output))})

    @app.post('/preview/artwork')
    def artwork(body: Artwork):
        if not body.remove:
            p = checked_path(body.image, True)
            if p.stat().st_size > 20 * 1024 * 1024: raise ValueError('Artwork must be smaller than 20 MB.')
            data = p.read_bytes()
            if not (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff')): raise ValueError('Choose PNG or JPEG artwork.')
        library = service.library(body.profile); items = []
        for tid in body.ids:
            track = library.tracks.get(tid)
            if not track: raise ValueError('Track not found.')
            path = legacy.file_uri_to_path(track.location or '')
            if not path: raise ValueError('No local media.')
            items.append({'id': tid, 'path': str(path), 'signature': signature(path)})
        return service.save_preview('artwork', body.profile, {'items': items, 'image': body.image, 'remove': body.remove})

    @app.post('/commit')
    def commit(body: Confirm): return {'job': service.commit(body.preview)}

    @app.post('/verify')
    def verify(body: Selection):
        library = service.library(body.profile)
        if any(i not in library.tracks for i in body.ids): raise ValueError('Track not found.')
        return {'job': service.jobs.enqueue('verify', body.model_dump())}

    @app.get('/jobs')
    def jobs():
        rows = service.store.rows('SELECT * FROM jobs WHERE archived=0 ORDER BY created DESC LIMIT 200')
        for r in rows:
            r['profile'] = json.loads(r['payload']).get('profile')
            r.pop('payload', None)
            if r['status'] != 'complete': r['progress'] = min(99, r['progress'])
            now = time.time()
            r['sampled_at'] = now
            r['elapsed_seconds'] = r['elapsed'] + (max(0, now - r['active_since']) if r['active_since'] else 0)
            if r['result']: r['result'] = json.loads(r['result'])
        return rows

    @app.post('/jobs/clear')
    def clear_queue(): return service.jobs.clear()

    @app.post('/jobs/{identity}/control')
    def control(identity: str, body: Control): return {'job': service.jobs.control(identity, body.action)}

    @app.get('/history')
    def history(q: str = ''):
        rows = service.store.rows('SELECT * FROM history WHERE created>? AND (kind LIKE ? OR detail LIKE ?) ORDER BY created DESC LIMIT 500', (service.store.setting('history_hidden_before', 0), f'%{q}%', f'%{q}%'))
        for r in rows: r['detail'] = json.loads(r['detail'])
        return rows

    @app.post('/history/clear')
    def clear_history(body: ConfirmRemoval):
        service.store.set_setting('history_hidden_before', time.time())
        return {'cleared': True, 'note': 'The visible list is clear. Undo records, file restores and the audit log are kept.'}

    @app.get('/edits')
    def edits(): return service.store.rows('SELECT * FROM edits ORDER BY created DESC LIMIT 1000')

    @app.get('/transfers')
    def transfers(): return service.store.rows('SELECT * FROM transfers ORDER BY created DESC LIMIT 1000')

    @app.get('/settings')
    def settings(): return service.store.setting('preferences', {'theme': 'Apple Light', 'template': '{artist}/{album}/{track} - {title}', 'low_confidence': .80, 'high_confidence': .92})

    @app.post('/settings')
    def save_settings(body: dict):
        default = body.get('default_xml_path', '')
        if not isinstance(default, str) or len(default) > 4096 or '\x00' in default:
            raise ValueError('Choose a valid default XML path.')
        low, high = body.get('low_confidence', .80), body.get('high_confidence', .92)
        if not (0 < low <= high <= 1): raise ValueError('Duplicate thresholds must satisfy 0 < low <= high <= 1.')
        if any(any(s in k.lower() for s in ('password', 'token', 'secret', 'api_key')) for k in body): raise ValueError('Credentials are not accepted by the preferences endpoint.')
        scale = body.get('text_scale', 100)
        if not isinstance(scale, (int, float)) or not 25 <= scale <= 400: raise ValueError('Text size must be between 25% and 400%.')
        service.store.set_setting('preferences', body); return body

    @app.post('/settings/import')
    def import_settings(body: SettingsImport): return service.import_settings(body.path, body.kind)

    @app.get('/rules')
    def rules(): return {'custom': [{'pattern': p, 'target': t} for p, t in legacy.genre_rules.load_custom_patterns()], 'builtin': [{'pattern': p, 'target': t} for p, t in legacy.genre_rules.PATTERNS]}

    @app.post('/rules')
    def save_rules(body: Rules):
        errors = []
        if body.csv is not None:
            parsed, errors = legacy.genre_rules.parse_patterns_csv(body.csv)
            values = legacy.genre_rules.load_custom_patterns().copy()
            for p, t in parsed:
                existing = next((i for i, row in enumerate(values) if row[0] == p), None)
                if existing is None: values.append((p, t))
                else: values[existing] = (p, t)
        else:
            values = [(str(r['pattern']), str(r['target'])) for r in (body.rules or [])]
            if any(not p.strip() or not t.strip() for p, t in values): raise ValueError('Pattern and target cannot be empty.')
        legacy.genre_rules.save_custom_patterns(values)
        return {'saved': len(values), 'errors': errors}

    @app.post('/rules/test')
    def test_rule(body: RuleTest): return {'result': legacy.genre_rules.preview_genre_mapping(body.genre, body.pattern or None, body.target or None), 'shadow': legacy.genre_rules.find_shadowing_rule(body.pattern) if body.pattern else None}

    @app.post('/playlists/export')
    def export_playlist(body: PlaylistExport): return service.playlist_export(body.profile, body.index, body.output)

    @app.post('/preview/playlist')
    def import_playlist(body: PlaylistImport): return service.playlist_import(body.profile, body.source, body.name)

    @app.post('/metadata/inspect')
    def inspect(body: PathRequest): return metadata.inspect(body.path)

    @app.post('/artwork/read')
    def read_artwork(body: PathRequest):
        image = legacy.read_embedded_artwork(checked_path(body.path, True))
        return {'image': base64.b64encode(image).decode() if image else None}

    @app.post('/spotify/compare')
    def spotify(body: PlaylistImport):
        provider = legacy.SpotifyExportProvider(); library = service.library(body.profile)
        tracks = list(provider.import_tracks(body.source)); playlists = list(provider.import_playlists(body.source))
        local = {(t.artist.casefold(), t.name.casefold()) for t in library.tracks.values()}
        return {'tracks': len(tracks), 'playlists': len(playlists), 'unmatched': [{'artist': t.artist, 'name': t.name} for t in tracks if (t.artist.casefold(), t.name.casefold()) not in local]}

    @app.post('/reports/export')
    def report(body: PathRequest):
        output = checked_path(body.path)
        with open(output, 'x', encoding='utf-8') as f:
            json.dump({'version': '3.1.1', 'history': history(), 'edits': edits(), 'transfers': transfers()}, f, indent=2, ensure_ascii=False)
        return {'output': str(output)}

    @app.get('/changelog')
    def changelog():
        path = Path(__file__).resolve().parents[1] / 'CHANGELOG.md'
        return {'text': path.read_text(encoding='utf-8')}

    return app
