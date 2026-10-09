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
from pydantic import BaseModel, Field, ConfigDict
from .service import Service
from . import legacy, metadata
from .com_service import run_com, FIELDS
from .filesystem import AUDIO, checked_path, signature


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Profile(Model):
    name: str = Field(min_length=1, max_length=200)
    source: str = ''
    kind: Literal['xml', 'folder', 'live'] = 'xml'
    roots: list[str] = Field(default_factory=list)


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

    app = FastAPI(title='Unified iTunes Library Manager', version='1.0.0', dependencies=[Depends(auth)], lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return Response(json.dumps({'detail': str(exc)}), status_code=400, media_type='application/json')

    @app.exception_handler(OSError)
    async def os_error(request, exc):
        return Response(json.dumps({'detail': str(exc)}), status_code=400, media_type='application/json')

    @app.get('/health')
    def health(): return {'ready': True, 'version': '1.0.0'}

    @app.get('/discovery')
    def discover():
        paths = legacy.default_library_xml_candidates()
        music = Path.home() / 'Music'
        return {'xml': [{'path': str(p), 'exists': p.exists()} for p in paths], 'databases': [{'path': str(music / 'iTunes' / 'iTunes Library.itl'), 'editable': False}], 'live_note': 'Classic iTunes on Windows only. Apple Music proprietary databases are read-only/unsupported; export XML or scan media.'}

    @app.get('/com/status')
    def com_status():
        try: return run_com({'operation': 'status'}, service.store.path, timeout=5)
        except Exception as exc: return {'available': False, 'reason': str(exc)}

    @app.get('/profiles')
    def profiles(): return [service.profile(row['id']) for row in service.store.rows('SELECT id FROM profiles ORDER BY name')]

    @app.post('/profiles')
    def profile(body: Profile):
        identity = service.add_profile(body.name, body.source, body.kind, body.roots)
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

    @app.get('/profiles/{identity}/overview')
    def overview(identity: str): return service.overview(identity)

    @app.get('/profiles/{identity}/duplicates')
    def duplicates(identity: str, mode: Literal['metadata', 'hash', 'fingerprint'] = 'metadata'): return service.duplicates(identity, mode)

    @app.get('/profiles/{identity}/playlists')
    def playlists(identity: str): return service.playlists(identity)

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
        rows = service.store.rows('SELECT * FROM jobs ORDER BY created DESC LIMIT 200')
        for r in rows:
            r.pop('payload', None)
            if r['result']: r['result'] = json.loads(r['result'])
        return rows

    @app.post('/jobs/{identity}/control')
    def control(identity: str, body: Control): return {'job': service.jobs.control(identity, body.action)}

    @app.get('/history')
    def history(q: str = ''):
        rows = service.store.rows('SELECT * FROM history WHERE kind LIKE ? OR detail LIKE ? ORDER BY created DESC LIMIT 500', (f'%{q}%', f'%{q}%'))
        for r in rows: r['detail'] = json.loads(r['detail'])
        return rows

    @app.get('/edits')
    def edits(): return service.store.rows('SELECT * FROM edits ORDER BY created DESC LIMIT 1000')

    @app.get('/transfers')
    def transfers(): return service.store.rows('SELECT * FROM transfers ORDER BY created DESC LIMIT 1000')

    @app.get('/settings')
    def settings(): return service.store.setting('preferences', {'theme': 'Apple Light', 'template': '{artist}/{album}/{track} - {title}', 'low_confidence': .80, 'high_confidence': .92})

    @app.post('/settings')
    def save_settings(body: dict):
        low, high = body.get('low_confidence', .80), body.get('high_confidence', .92)
        if not (0 < low <= high <= 1): raise ValueError('Duplicate thresholds must satisfy 0 < low <= high <= 1.')
        if any(any(s in k.lower() for s in ('password', 'token', 'secret', 'api_key')) for k in body): raise ValueError('Credentials are not accepted by the preferences endpoint.')
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
            json.dump({'version': '1.0.0', 'history': history(), 'edits': edits(), 'transfers': transfers()}, f, indent=2, ensure_ascii=False)
        return {'output': str(output)}

    @app.get('/changelog')
    def changelog():
        path = Path(__file__).resolve().parents[1] / 'CHANGELOG.md'
        return {'text': path.read_text(encoding='utf-8')}

    return app
