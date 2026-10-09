from __future__ import annotations
import shutil
from pathlib import Path
import mutagen
from mutagen.id3 import ID3, APIC
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover
from .com_service import validate_fields
from .filesystem import checked_path, signature, digest

TAGS = {'name': 'title', 'artist': 'artist', 'album': 'album', 'album_artist': 'albumartist', 'genre': 'genre', 'year': 'date', 'track': 'tracknumber', 'disc': 'discnumber', 'composer': 'composer'}


def inspect(path):
    path = checked_path(path, True)
    audio = mutagen.File(path, easy=True)
    if audio is None: raise ValueError('Unsupported or corrupt audio file.')
    info = audio.info
    return {'tags': {key: audio.get(tag, []) for key, tag in TAGS.items()},
            'codec': type(audio).__name__, 'duration': getattr(info, 'length', 0),
            'bitrate': getattr(info, 'bitrate', 0), 'sample_rate': getattr(info, 'sample_rate', 0),
            'channels': getattr(info, 'channels', 0), 'size': path.stat().st_size}


def write_file(change, store, job, data_dir):
    path = checked_path(change['path'], True)
    if path.suffix.lower() == '.m4p': raise ValueError('Protected DRM media cannot be edited.')
    if 'restore_values' in change:
        if not change['fields'] or any(k not in TAGS for k in change['restore_values']): raise ValueError('Unsupported undo fields.')
        if any(not isinstance(v, list) or any(not isinstance(x, str) for x in v) for v in change['restore_values'].values()): raise ValueError('Invalid stored tag backup.')
    else: validate_fields(change['fields'])
    if any(k not in TAGS for k in change['fields']):
        raise ValueError('This field is supported by live iTunes only; file tag writing supports title, artist, album, album artist, genre, year, track, disc and composer.')
    if signature(path) != change['signature']: raise ValueError('Audio changed since preview.')
    audio = mutagen.File(path, easy=True)
    if audio is None: raise ValueError('Unsupported or corrupt audio.')
    if getattr(audio.info, 'codec', '') in ('drms', 'drmi'): raise ValueError('Protected DRM media cannot be edited.')
    if audio.tags is None: audio.add_tags()
    for field, expected in change.get('expected_tags', {}).items():
        if list(audio.get(TAGS[field], [])) != expected: raise ValueError(f'{field} changed after the original edit; undo skipped.')
    backup = data_dir / 'backups' / job / (change['pid'] or str(change['id'])) / path.name
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)
    if digest(backup) != change['signature']['sha256']: raise ValueError('Backup verification failed.')
    journals = []
    for field, value in change['fields'].items():
        old = list(audio.get(TAGS[field], []))
        new = change.get('restore_values', {}).get(field, [str(value)] if value != '' else [])
        identity = store.journal(job, change['pid'], str(path), field, old, new)
        journals.append(identity)
        if new: audio[TAGS[field]] = new
        elif TAGS[field] in audio: del audio[TAGS[field]]
    try:
        audio.save()
        readback = mutagen.File(path, easy=True)
        for identity, (field, value) in zip(journals, change['fields'].items()):
            expected = change.get('restore_values', {}).get(field, [str(value)] if value != '' else [])
            if list(readback.get(TAGS[field], [])) != expected: raise ValueError('Metadata readback mismatch.')
            store.finish_edit(identity, 'applied')
    except Exception as exc:
        for identity in journals: store.finish_edit(identity, 'uncertain', str(exc))
        raise
    return {'pid': change['pid'], 'fields': change['fields'], 'errors': [], 'backup': str(backup)}


def write_artwork(path, image, remove=False):
    path = checked_path(path, True)
    if path.suffix.lower() == '.m4p': raise ValueError('Protected DRM media cannot be edited.')
    audio = mutagen.File(path)
    if isinstance(audio, MP4):
        if remove: audio.pop('covr', None)
        else:
            data = checked_path(image, True).read_bytes()
            fmt = MP4Cover.FORMAT_PNG if data.startswith(b'\x89PNG') else MP4Cover.FORMAT_JPEG
            audio['covr'] = [MP4Cover(data, imageformat=fmt)]
    elif isinstance(audio, FLAC):
        audio.clear_pictures()
        if not remove:
            data = checked_path(image, True).read_bytes()
            picture = Picture(); picture.type = 3; picture.data = data
            picture.mime = 'image/png' if data.startswith(b'\x89PNG') else 'image/jpeg'
            audio.add_picture(picture)
    elif audio is not None and isinstance(audio.tags, ID3):
        audio.tags.delall('APIC')
        if not remove:
            data = checked_path(image, True).read_bytes()
            audio.tags.add(APIC(encoding=3, mime='image/png' if data.startswith(b'\x89PNG') else 'image/jpeg', type=3, desc='Cover', data=data))
    else: raise ValueError('Artwork writing supports tagged MP3, M4A/MP4 and FLAC.')
    audio.save()
