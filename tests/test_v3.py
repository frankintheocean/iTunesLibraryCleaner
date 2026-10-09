"""Regression checks for saved libraries, live identity, search and task timing."""
import json
import plistlib
import threading
import time
from types import SimpleNamespace
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.com_service import find_track, scan_library, write_tracks
from backend.jobs import Jobs
from backend.store import Store
from test_manager import TOKEN, scanned, wait, service


def test_task_stays_below_100_until_final_save(tmp_path):
    store=Store(tmp_path/'db');saving=threading.Event();finish=threading.Event()
    def handler(kind,payload,job,checkpoint):
        checkpoint(job,10,10,'Saving');saving.set();finish.wait(3);return {}
    jobs=Jobs(store,handler)
    try:
        job=jobs.enqueue('metadata',{'changes':[{}]});assert saving.wait(2)
        row=store.rows('SELECT * FROM jobs WHERE id=?',(job,))[0]
        assert row['status']=='running' and row['progress']==99 and row['eta_end'] is not None
        finish.set()
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            row=store.rows('SELECT * FROM jobs WHERE id=?',(job,))[0]
            if row['status']=='complete':break
            time.sleep(.01)
        assert row['status']=='complete' and row['progress']==100
    finally:finish.set();jobs.close()


def test_eta_deadline_does_not_move_forward(tmp_path):
    store=Store(tmp_path/'db');jobs=Jobs(store,lambda *args:None);jobs.close()
    job=jobs.enqueue('scan',{})
    store.execute("UPDATE jobs SET status='running',elapsed=10,eta_end=100 WHERE id=?",(job,))
    jobs.stop.clear()
    jobs.checkpoint(job,10,100)
    first=store.rows('SELECT eta_end,progress FROM jobs WHERE id=?',(job,))[0]
    store.execute('UPDATE jobs SET elapsed=20 WHERE id=?',(job,))
    jobs.checkpoint(job,11,100)
    second=store.rows('SELECT eta_end,progress FROM jobs WHERE id=?',(job,))[0]
    assert second['eta_end']<=first['eta_end']
    assert second['eta_end']-20<first['eta_end']-10
    jobs.checkpoint(job,1,10,'New phase')
    assert store.rows('SELECT progress FROM jobs WHERE id=?',(job,))[0]['progress']==second['progress']


def test_snapshot_can_save_while_old_file_is_open(service,tmp_path):
    identity,media,_=scanned(service,tmp_path)
    old=service.snapshot_path(identity)
    with old.open('rb') as held:
        library=service.library(identity);library.tracks[1].raw['Name']='After'
        service.save_snapshot(identity,library)
        assert held.read() and old.exists()
        assert service.snapshot_path(identity)!=old
        assert service.library(identity).tracks[1].name=='After'
        assert plistlib.loads(service.snapshot_path(identity).read_bytes())['Tracks']['1']['Name']=='After'
    assert media.exists()


def test_snapshot_failure_keeps_old_pointer(service,tmp_path,monkeypatch):
    from backend import service as module
    identity,_,_=scanned(service,tmp_path);old=service.snapshot_path(identity)
    def deny(*args):raise PermissionError('Locked temporary file')
    monkeypatch.setattr(module.os,'replace',deny);monkeypatch.setattr(module.time,'sleep',lambda _:None)
    with pytest.raises(PermissionError):service.save_snapshot(identity,service.library(identity))
    assert service.snapshot_path(identity)==old and service.library(identity).tracks[1].name=='Song'


def test_cached_libraries_are_independent_and_read_once(service,tmp_path,monkeypatch):
    from backend import service as module
    identity,_,_=scanned(service,tmp_path);service._libraries.clear();calls=[]
    original=module.legacy.Library.load
    def load(*args,**kwargs):calls.append(args[0]);return original(*args,**kwargs)
    monkeypatch.setattr(module.legacy.Library,'load',load)
    library=service.library(identity);library.tracks[1].raw['Name']='Unsaved'
    assert service.library(identity).tracks[1].name=='Song'
    service.overview(identity);service.playlists(identity)
    assert len(calls)==1


def test_edit_does_not_reindex_unchanged_tracks(service,tmp_path,monkeypatch):
    identity,_,_=scanned(service,tmp_path)
    preview=service.metadata_preview(identity,[1],{'genre':'Pop'},'file')
    monkeypatch.setattr(service,'index',lambda *args:pytest.fail('Full reindex during one-song edit'))
    row=wait(service,service.commit(preview['id']))
    assert row['status']=='complete',row['error']
    assert service.tracks(identity,'Pop')['total']==2
    assert service.tracks(identity,'Trap')['total']==0
    assert service.overview(identity)['size']>0


def test_live_lookup_falls_back_to_verified_name_without_walking():
    good=SimpleNamespace(Name='Coffee',pid='B140BDDD2AB311CA')
    class Tracks:
        def ItemByPersistentID(self,*args):return None
        def ItemByName(self,name):assert name=='Coffee';return good
        def __iter__(self):pytest.fail('Unnecessary full-library search')
    app=SimpleNamespace(LibraryPlaylist=SimpleNamespace(Tracks=Tracks()),ITObjectPersistentIDHigh=lambda t:int(t.pid[:8],16),ITObjectPersistentIDLow=lambda t:int(t.pid[8:],16))
    assert find_track(app,good.pid,name='Coffee') is good


def test_live_lookup_never_edits_another_track_with_the_same_title(tmp_path):
    wrong=SimpleNamespace(Name='Coffee',Genre='Jazz',pid='0000000000000001')
    good=SimpleNamespace(Name='Coffee',Genre='Indie',pid='B140BDDD2AB311CA')
    class Tracks:
        def ItemByPersistentID(self,*args):return wrong
        def ItemByName(self,name):return wrong
        def __iter__(self):return iter([wrong,good])
    app=SimpleNamespace(LibraryPlaylist=SimpleNamespace(Tracks=Tracks()),ITObjectPersistentIDHigh=lambda t:int(t.pid[:8],16),ITObjectPersistentIDLow=lambda t:int(t.pid[8:],16))
    result=write_tracks(lambda:app,[{'pid':good.pid,'name':'Coffee','expected':{'genre':'Indie'},'fields':{'genre':'Pop'}}],Store(tmp_path/'db'),'job')
    assert not result[0]['errors'] and good.Genre=='Pop' and wrong.Genre=='Jazz'
    with pytest.raises(ValueError,match='currently open'):find_track(app,'0000000000000002',name='Coffee')


def test_scan_rejects_a_library_changed_mid_scan():
    song=SimpleNamespace(Name='Song',TrackDatabaseID=42)
    class Tracks:
        Count=1
        def __iter__(self):return iter([song])
    library=SimpleNamespace(Tracks=Tracks(),Source=SimpleNamespace(Playlists=[]))
    reads=[]
    def low(obj):
        if obj is library:reads.append(1);return len(reads)
        return 42
    app=SimpleNamespace(LibraryPlaylist=library,ITObjectPersistentIDHigh=lambda obj:0,ITObjectPersistentIDLow=low)
    with pytest.raises(ValueError,match='changed during'):scan_library(app)


def test_xml_size_uses_files_when_export_omits_sizes(service,tmp_path):
    identity,media,_=scanned(service,tmp_path)
    overview=service.overview(identity)
    assert overview['size']==media.stat().st_size*2 and overview['unknown_sizes']==0


def test_remove_history_default_path_and_playlist_picture(tmp_path):
    from test_manager import flac,xml
    source=xml(tmp_path/'OutsideMusic.xml',flac(tmp_path/'song.flac'))
    app=create_app(tmp_path/'data',TOKEN)
    with TestClient(app,headers={'Authorization':'Bearer '+TOKEN}) as client:
        service=app.state.service;identity=service.add_profile('Saved',str(source),'xml');service.scan(identity,'fixture',lambda *args:None)
        journal=service.store.journal('fixture','pid','live','name','Before','After')
        service.store.audit('fixture',{'job':'fixture'})
        assert client.post('/history/clear',json={'confirmed':True}).status_code==200
        assert client.get('/history').json()==[]
        assert service.store.rows('SELECT id FROM history') and service.store.rows('SELECT id FROM edits WHERE id=?',(journal,))
        assert client.post('/settings',json={'default_xml_path':str(source)}).status_code==200
        assert client.get('/discovery').json()['xml'][0]=={'path':str(source),'exists':True}
        image=tmp_path/'playlist.png';Image.new('RGB',(100,100),'blue').save(image)
        assert client.post(f'/profiles/{identity}/playlist-cover',json={'index':0,'image':str(image)}).status_code==200
        assert client.get(f'/profiles/{identity}/playlists').json()[0]['image'].startswith('data:image/jpeg;')
        assert client.post(f'/profiles/{identity}/remove',json={'confirmed':False}).status_code==422
        assert client.post(f'/profiles/{identity}/remove',json={'confirmed':True}).status_code==200
        assert client.get('/profiles').json()==[]
        assert source.exists() and service.snapshot_path(identity).exists()
        assert service.store.rows('SELECT id FROM edits WHERE id=?',(journal,))


def test_cannot_remove_a_library_with_active_work(service,tmp_path):
    identity,_,_=scanned(service,tmp_path);service.jobs.close()
    service.jobs.enqueue('scan',{'profile':identity})
    with pytest.raises(ValueError,match='tasks to finish'):service.remove_profile(identity)
    assert not service.profile(identity)['config'].get('removed')


def test_com_error_is_json(tmp_path,monkeypatch):
    import backend.service as module
    def unavailable(*args,**kwargs):raise RuntimeError('iTunes is busy. Try again.')
    app=create_app(tmp_path/'data',TOKEN)
    with TestClient(app,headers={'Authorization':'Bearer '+TOKEN},raise_server_exceptions=False) as client:
        monkeypatch.setattr(app.state.service,'metadata_preview',unavailable)
        response=client.post('/preview/metadata',json={'profile':'fixture','ids':[1],'fields':{'genre':'Pop'}})
        assert response.status_code==503 and response.json()['detail']=='iTunes is busy. Try again.'


def test_database_handles_close_and_failed_transactions_roll_back(tmp_path):
    import sqlite3
    store=Store(tmp_path/'manager.sqlite')
    with store.connect() as db:
        db.execute("INSERT INTO settings VALUES('keep','1')")
    assert store.setting('keep')==1
    with pytest.raises(sqlite3.ProgrammingError,match='closed database'):
        db.execute('SELECT 1')
    with pytest.raises(RuntimeError,match='Abort'):
        with store.connect() as failed:
            failed.execute("INSERT INTO settings VALUES('discard','2')")
            raise RuntimeError('Abort')
    assert store.setting('discard') is None and store.setting('keep')==1
    with pytest.raises(sqlite3.ProgrammingError,match='closed database'):
        failed.execute('SELECT 1')
    # Removing a closed database must also work on Windows, not only on Unix.
    store.path.unlink()
