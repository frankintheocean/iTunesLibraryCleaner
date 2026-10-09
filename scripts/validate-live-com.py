"""Real iTunes acceptance on Windows; refuses a nonempty library.

Start classic iTunes using a NEW empty disposable library (hold Shift at launch).
This adds two synthetic WAV tracks and leaves them in that test library for review.
No existing track is edited or deleted. Run from the project root with its venv.
"""
from __future__ import annotations
import argparse
import json
import multiprocessing
import sys
import time
import uuid
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.com_service import FIELDS, pid_for, run_com, split_pid
from backend.service import Service
from backend.filesystem import digest


def wait_job(service, identity, timeout=330):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = service.store.rows('SELECT * FROM jobs WHERE id=?', (identity,))[0]
        if job['status'] == 'complete':
            return json.loads(job['result'])
        if job['status'] in ('failed', 'interrupted', 'cancelled'):
            raise RuntimeError(job['error'] or job['status'])
        time.sleep(.1)
    raise TimeoutError('Validation job did not finish; inspect the saved journal before retrying.')


def apply_preview(service, preview):
    identity = service.commit(preview['id'])
    wait_job(service, identity)
    edits = service.store.rows('SELECT status,error FROM edits WHERE job=?', (identity,))
    if any(edit['status'] != 'applied' for edit in edits):
        raise AssertionError(f'Live edit was not verified: {edits}')
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--empty-test-library', action='store_true', required=True,
                        help='Acknowledge that classic iTunes is running with a new empty disposable library.')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/live-com-validation')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('Real COM validation requires Windows and classic iTunes; mocks are not used.')
    import pythoncom
    import win32com.client
    args.output.mkdir(parents=True, exist_ok=True)
    workspace = args.output / uuid.uuid4().hex
    workspace.mkdir()
    report = {'result': 'failed', 'checks': [], 'workspace': str(workspace),
              'not_tested': ['modal dialogs', 'iTunes restart/reconnect', 'locked/read-only media',
                             'missing tracks', 'DRM', 'high-DPI/multi-monitor', 'Windows 10/11 matrix',
                             'album grouping/merge', 'genre-rule normalization', 'packaged COM worker']}
    service = None
    pythoncom.CoInitialize()
    try:
        app = win32com.client.GetActiveObject('iTunes.Application')
        report['itunes_version'] = app.Version
        if app.LibraryPlaylist.Tracks.Count != 0:
            raise RuntimeError('Refusing validation: iTunes library must be empty. Create a disposable library first.')
        fixtures = []
        for i in range(2):
            media = workspace / f'synthetic-{i + 1}.wav'
            with wave.open(str(media), 'wb') as audio:
                audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(44100)
                audio.writeframes(b'\0\0' * 44100)
            operation = app.LibraryPlaylist.AddFile(str(media))
            deadline = time.monotonic() + 30
            while operation.InProgress:
                if time.monotonic() > deadline:
                    raise TimeoutError('iTunes did not finish adding the synthetic WAV.')
                pythoncom.PumpWaitingMessages(); time.sleep(.1)
            if operation.Tracks.Count != 1:
                raise AssertionError('iTunes did not import exactly one synthetic track.')
            track = operation.Tracks.Item(1)
            imported = Path(track.Location).resolve()
            if digest(imported) != digest(media):
                raise AssertionError('Imported media differs from the generated WAV; refusing to edit.')
            fixtures.append({'pid': pid_for(app, track), 'path': str(imported), 'source': str(media.resolve())})
        service = Service(workspace / 'state')
        status = run_com({'operation': 'status'}, service.store.path)
        if not status['available'] or status['tracks'] != 2:
            raise AssertionError('Isolated COM process could not see the two test tracks.')
        report['checks'].append('real active-object connection from isolated COM process')
        profile = service.add_profile('Disposable COM validation', '', 'live')
        wait_job(service, service.jobs.enqueue('scan', {'profile': profile}))
        library = service.library(profile)
        by_pid = {track.raw['Persistent ID']: track for track in library.tracks.values()}
        if set(by_pid) != {item['pid'] for item in fixtures}:
            raise AssertionError('Live scan identity mismatch; refusing to edit.')
        for item in fixtures:
            # Verify the exact newly generated file is still bound to its persistent ID.
            track = app.LibraryPlaylist.Tracks.ItemByPersistentID(*split_pid(item['pid']))
            if Path(track.Location).resolve() != Path(item['path']):
                raise AssertionError('Fixture location mismatch; refusing to edit.')
        report['checks'].append('real live scan, playlists, generated file paths and persistent-ID lookup')
        fixture = fixtures[0]
        identity = by_pid[fixture['pid']].track_id
        fields = {'genre': 'Indie', 'name': 'COM Test Song', 'artist': 'Synthetic Artist',
                  'album': 'Synthetic Album', 'album_artist': 'Synthetic Album Artist',
                  'year': 2026, 'track': 1, 'track_count': 2, 'disc': 1, 'disc_count': 1,
                  'composer': 'Synthetic Composer', 'comment': 'Disposable validation only',
                  'compilation': True, 'rating': 80}
        original = {key: by_pid[fixture['pid']].raw[FIELDS[key][1]] for key in fields}
        job = apply_preview(service, service.metadata_preview(profile, [identity], fields, 'live'))
        track = app.LibraryPlaylist.Tracks.ItemByPersistentID(*split_pid(fixture['pid']))
        if any(getattr(track, FIELDS[key][0]) != value for key, value in fields.items()):
            raise AssertionError('Independent live COM readback mismatch.')
        report['checks'].append('preview/queue/journal/readback of all 14 supported live metadata fields')
        # Undo restores only unchanged values: simulate an external edit to this fixture.
        track.Genre = 'External synthetic edit'
        apply_preview(service, service.undo_preview(profile, job))
        for key, value in original.items():
            expected = 'External synthetic edit' if key == 'genre' else value
            if getattr(track, FIELDS[key][0]) != expected:
                raise AssertionError(f'Conditional undo mismatch: {key}')
        report['checks'].append('conditional undo restores other fields and preserves external genre edit')
        # Restore that synthetic edit, using an explicit current-value expectation.
        result = run_com({'operation': 'edit', 'changes': [{
            'pid': fixture['pid'], 'fields': {'genre': original['genre']},
            'expected': {'genre': 'External synthetic edit'}}]}, service.store.path, 'fixture-restore')
        if result[0]['errors']:
            raise AssertionError(result)
        report['checks'].append('fixture genre restored with expected-value verification')
        report['persistent_ids'] = [item['pid'] for item in fixtures]
        report['signed_high_bit_id_exercised'] = any(
            any(part < 0 for part in split_pid(item['pid'])) for item in fixtures)
        report['result'] = 'passed'
        print('PASS: real iTunes COM metadata edits, independent readback and conditional undo.')
    except Exception as exc:
        report['error'] = str(exc)
        raise
    finally:
        if service is not None:
            service.jobs.close()
        pythoncom.CoUninitialize()
        path = workspace / 'report.json'
        path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f'Validation report and journal: {workspace}')
        print('Synthetic WAVs and test-library entries are retained; no tracks were deleted.')


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
