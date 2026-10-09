import base64
import json
import threading
import time
from io import BytesIO
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.artwork import encode_thumbnail, thumbnail
from backend.jobs import Jobs
from backend.store import Store

TOKEN='test-session-token-that-is-long-enough-123456'

def test_clear_keeps_active_work_and_undo_records(tmp_path):
    store=Store(tmp_path/'db');started=threading.Event();finish=threading.Event();calls=[]
    def handler(kind,payload,identity,checkpoint):
        calls.append(identity);started.set();finish.wait(5);return {'ok':True}
    jobs=Jobs(store,handler)
    try:
        running=jobs.enqueue('verify',{});assert started.wait(2)
        waiting=jobs.enqueue('verify',{})
        record=store.journal(running,'pid','file','genre','Old','New')
        outcome=jobs.clear();assert outcome['cancelled']==1
        assert store.rows('SELECT status,archived FROM jobs WHERE id=?',(waiting,))[0]=={'status':'cancelled','archived':1}
        assert store.rows('SELECT status,archived FROM jobs WHERE id=?',(running,))[0]=={'status':'running','archived':0}
        assert store.rows('SELECT id FROM edits WHERE id=?',(record,))
        finish.set()
        deadline=time.monotonic()+2
        while time.monotonic()<deadline and store.rows('SELECT status FROM jobs WHERE id=?',(running,))[0]['status']=='running':time.sleep(.01)
        assert calls==[running]
        jobs.clear();assert not store.rows('SELECT id FROM jobs WHERE archived=0')
        assert store.rows('SELECT id FROM history')
    finally:finish.set();jobs.close()

def test_pause_freezes_active_elapsed(tmp_path):
    store=Store(tmp_path/'db');jobs=Jobs(store,lambda *args:None);jobs.close()
    identity=jobs.enqueue('scan',{})
    store.execute("UPDATE jobs SET status='running',started=?,active_since=?,elapsed=10 WHERE id=?",(time.time()-100,time.time()-5,identity))
    jobs.control(identity,'pause')
    first=store.rows('SELECT elapsed,active_since FROM jobs WHERE id=?',(identity,))[0]
    assert 14<=first['elapsed']<=16 and first['active_since'] is None
    jobs.control(identity,'resume');jobs.control(identity,'cancel')
    final=store.rows('SELECT elapsed,active_since,finished FROM jobs WHERE id=?',(identity,))[0]
    assert first['elapsed']<=final['elapsed']<=first['elapsed']+1
    assert final['active_since'] is None and final['finished']

def test_upgrade_preserves_jobs_and_preferences(tmp_path):
    import sqlite3
    path=tmp_path/'old.db'
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE jobs(id TEXT PRIMARY KEY,kind TEXT,payload TEXT,status TEXT,progress REAL DEFAULT 0,current TEXT DEFAULT '',result TEXT,error TEXT,created REAL,updated REAL,priority INTEGER DEFAULT 0,checkpoint INTEGER DEFAULT 0)")
        db.execute("INSERT INTO jobs(id,kind,status,created,updated) VALUES('old','scan','complete',1,2)")
    store=Store(path);store.set_setting('preferences',{'theme':'Apple Dark'})
    assert store.rows('SELECT id,archived,elapsed FROM jobs')[0]=={'id':'old','archived':0,'elapsed':0}
    assert Store(path).setting('preferences')['theme']=='Apple Dark'

def test_thumbnail_is_small_and_invalid_art_is_safe():
    source=BytesIO();Image.new('RGB',(800,600),'red').save(source,format='PNG')
    image=encode_thumbnail(source.getvalue());assert image.startswith('data:image/jpeg;base64,')
    with Image.open(BytesIO(base64.b64decode(image.split(',')[1]))) as cover:assert cover.size==(96,72)
    assert encode_thumbnail(b'not an image') is None
    assert thumbnail('/does/not/exist') is None

def test_artwork_and_preferences_endpoints(tmp_path):
    from mutagen.flac import FLAC,Picture
    from test_manager import flac,xml
    media=flac(tmp_path/'song.flac');source=xml(tmp_path/'library.xml',media)
    image=BytesIO();Image.new('RGB',(50,50),'blue').save(image,format='PNG')
    audio=FLAC(media);picture=Picture();picture.type=3;picture.mime='image/png';picture.data=image.getvalue();audio.add_picture(picture);audio.save()
    app=create_app(tmp_path/'data',TOKEN)
    with TestClient(app,headers={'Authorization':'Bearer '+TOKEN}) as client:
        service=app.state.service;identity=service.add_profile('Art',str(source),'xml');service.scan(identity,'fixture',lambda *args:None)
        result=client.get(f'/profiles/{identity}/artwork/1');assert result.status_code==200 and result.json()['image'].startswith('data:image/jpeg;')
        playlist=client.get(f'/profiles/{identity}/playlists').json()[0];assert playlist['tracks'][0]['id']==2
        assert client.post('/settings',json={'text_scale':400,'font_family':'Verdana','reduced_motion':True}).status_code==200
        assert client.get('/settings').json()['text_scale']==400
        assert client.post('/settings',json={'text_scale':401}).status_code==400
        assert client.get(f'/profiles/{identity}/artwork/999').status_code==400


def test_live_cover_uses_signed_ids_and_only_temporary_output():
    from types import SimpleNamespace
    from backend.com_service import read_live_artwork
    calls=[];outputs=[]
    def save(path):
        outputs.append(path);Image.new('RGB',(120,120),'green').save(path)
    artwork=SimpleNamespace(Count=1,Item=lambda index:SimpleNamespace(SaveArtworkToFile=save))
    def item(high,low):calls.append((high,low));return SimpleNamespace(Artwork=artwork)
    app=SimpleNamespace(LibraryPlaylist=SimpleNamespace(Tracks=SimpleNamespace(ItemByPersistentID=item)))
    assert read_live_artwork(app,'FFFFFFFF80000001').startswith('data:image/jpeg;')
    assert calls==[(-1,-2147483647)]
    from pathlib import Path
    assert outputs and not Path(outputs[0]).exists()
