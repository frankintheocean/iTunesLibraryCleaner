import json
import os
import plistlib
import time
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.com_service import split_pid, validate_fields, write_tracks, run_com
from backend.filesystem import signature, verified_transfer, organized_path, checked_path
from backend.store import Store
from backend.service import Service
from backend import metadata

TOKEN='test-session-token-that-is-long-enough-123456'

@pytest.fixture
def store(tmp_path):return Store(tmp_path/'db.sqlite')

@pytest.fixture
def service(tmp_path):
 s=Service(tmp_path/'data')
 yield s
 s.jobs.close()

def flac(path):
 # A synthetic FLAC STREAMINFO header, used only for metadata round-trip tests.
 bits=(44100<<44)|(1<<41)|(15<<36)|44100
 stream=b'\x10\x00\x10\x00'+b'\x00'*6+bits.to_bytes(8,'big')+b'\x00'*16
 path.write_bytes(b'fLaC'+b'\x80\x00\x00\x22'+stream)
 from mutagen.flac import FLAC
 audio=FLAC(path);audio['title']='Before';audio['artist']='Artist';audio['album']='Album';audio['genre']='Trap';audio['custom-field']='Preserve me';audio.save()
 return path

def xml(path, media):
 raw={'Tracks':{'1':{'Track ID':1,'Persistent ID':'FFFFFFFF80000001','Name':'Song','Artist':'Artist','Album':'Album','Genre':'Trap','Location':media.as_uri(),'Total Time':180000,'Bit Rate':320,'Play Count':2},'2':{'Track ID':2,'Persistent ID':'A1234567FEDCBA98','Name':'Song','Artist':'Artist','Album':'Album','Genre':'Hip Hop','Location':media.as_uri(),'Total Time':180000,'Bit Rate':128,'Play Count':3}},'Playlists':[{'Name':'Favorites','Playlist Items':[{'Track ID':2},{'Track ID':1}]}]}
 path.write_bytes(plistlib.dumps(raw));return path

def scanned(service,tmp_path):
 media=flac(tmp_path/'song.flac');source=xml(tmp_path/'Library.xml',media)
 identity=service.add_profile('Test',str(source),'xml')
 service.scan(identity,'scan-test',lambda *args:None)
 return identity,media,source

def wait(service,job):
 deadline=time.monotonic()+10
 while time.monotonic()<deadline:
  row=service.store.rows('SELECT * FROM jobs WHERE id=?',(job,))[0]
  if row['status'] not in ('queued','running','paused'):return row
  time.sleep(.01)
 raise AssertionError('Job did not finish')

@pytest.mark.parametrize('pid,parts',[('FFFFFFFF80000001',(-1,-2147483647)),('0000000000000001',(0,1)),('A1234567FEDCBA98',(-1591523993,-19088744))])
def test_signed_persistent_ids(pid,parts):assert split_pid(pid)==parts

@pytest.mark.parametrize('pid',['','1','x'*16,'0'*17,None])
def test_invalid_identity_is_rejected(pid):
 with pytest.raises(ValueError):split_pid(pid)

@pytest.mark.parametrize('fields',[{'Delete':True},{'year':-1},{'rating':101},{'year':'2025'},{'compilation':1},{'genre':'x\x00'}])
def test_metadata_allowlist(fields):
 with pytest.raises(ValueError):validate_fields(fields)

def fake_app(track):
 class Tracks:
  def ItemByPersistentID(self,high,low):
   assert (high,low)==(-1,-2147483647)
   return track
 return SimpleNamespace(LibraryPlaylist=SimpleNamespace(Tracks=Tracks()))

def test_live_appwide_edit_and_durable_journal(store):
 track=SimpleNamespace(Genre='Trap',Name='Old',Artist='Old artist',Album='Old album',AlbumArtist='Old AA')
 fields={'genre':'Hip-Hop/Rap','name':'New','artist':'New artist','album':'New album','album_artist':'New AA'}
 out=write_tracks(lambda:fake_app(track),[{'pid':'FFFFFFFF80000001','fields':fields}],store,'job')
 assert not out[0]['errors'] and track.Genre=='Hip-Hop/Rap' and track.Name=='New' and track.AlbumArtist=='New AA'
 records=store.rows('SELECT * FROM edits')
 assert len(records)==5 and {r['status'] for r in records}=={'applied'}
 assert json.loads(next(r for r in records if r['field']=='name')['old'])=='Old'

def test_changed_since_preview_is_skipped(store):
 track=SimpleNamespace(Genre='Changed by user')
 result=write_tracks(lambda:fake_app(track),[{'pid':'FFFFFFFF80000001','fields':{'genre':'Pop'},'expected':{'genre':'Trap'}}],store,'job')
 assert result[0]['errors'] and track.Genre=='Changed by user'
 assert not store.rows('SELECT * FROM edits')

def test_partial_com_write_and_readback_failure_are_explicit(store):
 class Track:
  Genre='Trap'
  @property
  def Name(self):return 'Locked'
  @Name.setter
  def Name(self,value):raise PermissionError('Locked file')
 t=Track();r=write_tracks(lambda:fake_app(t),[{'pid':'FFFFFFFF80000001','fields':{'genre':'Pop','name':'New'}}],store,'job')[0]
 assert r['fields']=={'genre':'Pop'} and r['errors']
 assert {r['status'] for r in store.rows('SELECT * FROM edits')}=={'applied','uncertain'}

def test_live_reconnect_busy_call(store):
 class Busy(Exception):hresult=-2147418111
 class Track:
  _genre='Trap';calls=0
  @property
  def Genre(self):return self._genre
  @Genre.setter
  def Genre(self,v):
   self.calls+=1
   if self.calls==1:raise Busy('busy')
   self._genre=v
 t=Track();r=write_tracks(lambda:fake_app(t),[{'pid':'FFFFFFFF80000001','fields':{'genre':'Pop'}}],store,'job')
 assert not r[0]['errors'] and t.calls==2

def test_nonwindows_live_has_actionable_failure(store):
 if os.name=='nt':pytest.skip('Linux-specific capability boundary')
 with pytest.raises(RuntimeError,match='Windows'):run_com({'operation':'status'},store.path)

def test_scan_duplicate_merge_preserves_playlist_and_original(service,tmp_path):
 identity,media,source=scanned(service,tmp_path);original=source.read_bytes()
 groups=service.duplicates(identity)
 assert len(groups)==1 and set(groups[0]['ids'])=={1,2}
 preview=service.merge_preview(identity,[{'ids':[1,2],'canonical_id':1}],str(tmp_path/'Cleaned.xml'))
 row=wait(service,service.commit(preview['id']));assert row['status']=='complete',row['error']
 from backend.legacy import Library
 cleaned=Library.load(tmp_path/'Cleaned.xml')
 assert list(cleaned.tracks)==[1] and cleaned.tracks[1].play_count==5
 assert cleaned.playlists[0].track_ids()==[1]
 assert source.read_bytes()==original and media.exists()

def test_preview_commit_only_once_and_stale_rejected(service,tmp_path):
 identity,_,_=scanned(service,tmp_path)
 p=service.metadata_preview(identity,[1],{'genre':'Pop'},'file')
 service.scan(identity,'fresh-scan',lambda *args:None)
 # Same source produces same snapshot, so force an actual change.
 library=service.library(identity);library.tracks[1].raw['Genre']='Other';service.save_snapshot(identity,library)
 with pytest.raises(ValueError,match='changed'):service.commit(p['id'])

def test_genre_rules_and_file_metadata_roundtrip(service,tmp_path):
 identity,media,_=scanned(service,tmp_path)
 p=service.cleaner_preview(identity,{'target':'file'})
 assert p['changes'][0]['fields']['genre']=='Hip-Hop/Rap'
 # Two library entries refer to the same file. Edit one explicitly.
 p=service.metadata_preview(identity,[1],{'name':'After','genre':'Pop'},'file')
 job=service.commit(p['id']);row=wait(service,job);assert row['status']=='complete',row['error']
 from mutagen.flac import FLAC
 audio=FLAC(media)
 assert audio['title']==['After'] and audio['custom-field']==['Preserve me']
 assert list((service.data_dir/'backups'/job).rglob('*.flac'))
 with pytest.raises(ValueError,match='already committed'):service.commit(p['id'])

def test_transfer_hash_quarantine_restore(store,tmp_path):
 source=tmp_path/'song.mp3';source.write_bytes(b'music'*1000);old=signature(source)
 destination=tmp_path/'quarantine'/'song.mp3'
 identity=verified_transfer(source,destination,old,'quarantine',store,'job')
 assert not source.exists() and signature(destination)['sha256']==old['sha256']
 verified_transfer(destination,source,signature(destination),'restore',store,'restore')
 assert source.read_bytes()==b'music'*1000 and not destination.exists()
 assert store.rows('SELECT * FROM transfers WHERE id=?',(identity,))[0]['status']=='complete'

def test_transfer_rejects_changed_file_and_existing_destination(store,tmp_path):
 source=tmp_path/'source';source.write_bytes(b'original');sig=signature(source);source.write_bytes(b'changed')
 with pytest.raises(ValueError,match='changed'):verified_transfer(source,tmp_path/'dest',sig,'move',store,'job')
 dest=tmp_path/'dest';dest.write_bytes(b'existing')
 with pytest.raises(ValueError,match='exists'):verified_transfer(source,dest,signature(source),'copy',store,'job')
 assert dest.read_bytes()==b'existing' and source.exists()

@pytest.mark.parametrize('template',['../{artist}/{title}','/{title}','{artist.__class__}/{title}','{unknown}/{title}','{title!r}'])
def test_traversal_templates_rejected(template):
 with pytest.raises(ValueError):organized_path(template,{'artist':'Artist','title':'Song'},'.mp3')

def test_unicode_reserved_and_illegal_names():
 p=organized_path('{artist}/{album}/{title}',{'artist':'Björk','album':'CON','title':'Hello: / World?'},'.flac')
 assert p.parts[0]=='Björk' and p.parts[1]=='_CON' and ':' not in str(p) and p.suffix=='.flac'

def test_symlink_rejected(tmp_path):
 source=tmp_path/'source';source.mkdir();link=tmp_path/'link';link.symlink_to(source)
 with pytest.raises(ValueError,match='Symlinks'):checked_path(link/'file')

def test_collision_and_overlap_rejected(service,tmp_path):
 source_dir=tmp_path/'source';source_dir.mkdir()
 identity,media,_=scanned(service,source_dir)
 with pytest.raises(ValueError,match='overlap'):service.transfer_preview(identity,[1],str(media.parent))
 root=tmp_path/'separate';root.mkdir();(root/'song.flac').write_bytes(b'existing')
 with pytest.raises(ValueError,match='collision'):service.transfer_preview(identity,[1],str(root),template='song')

def test_playlist_export_import_order(service,tmp_path):
 identity,media,_=scanned(service,tmp_path)
 out=tmp_path/'Favorites.m3u8';service.playlist_export(identity,0,str(out))
 assert out.read_text().count(str(media))==2
 p=service.playlist_import(identity,str(out),'Imported')
 row=wait(service,service.commit(p['id']));assert row['status']=='complete',row['error']
 from backend.legacy import Library
 library=Library.load(Path(p['output']))
 assert library.playlists[-1].name=='Imported' and len(library.playlists[-1].track_ids())==2

def test_settings_migration_preserves_unknown_and_excludes_secrets(service,tmp_path):
 path=tmp_path/'settings.json';path.write_text(json.dumps({'theme':'Midnight','custom_legacy_option':42,'lastfm_key':'must-not-export'}))
 service.import_settings(path,'cleaner');settings=service.store.setting('legacy_settings')['cleaner']
 assert settings['custom_legacy_option']==42 and 'lastfm_key' not in settings

def test_auth_confirmation_validation_and_rules(tmp_path):
 app=create_app(tmp_path/'api-data',TOKEN)
 with TestClient(app) as client:
  assert client.get('/health').status_code==401
  client.headers['Authorization']='Bearer '+TOKEN
  assert client.get('/health').json()['ready']
  assert client.post('/commit',json={'preview':'anything','confirmed':False}).status_code==422
  assert client.post('/settings',json={'low_confidence':.9,'high_confidence':.5}).status_code==400
  assert client.post('/rules',json={'csv':'pattern,target\nphonk,Custom\n,invalid'}).json()['errors']
  assert client.post('/rules/test',json={'genre':'phonk'}).json()['result']['result']=='Custom'
  if os.name!='nt':assert client.get('/com/status').json()['available'] is False

def test_interrupted_job_recovery(tmp_path):
 store=Store(tmp_path/'recovery.sqlite')
 store.execute("INSERT INTO jobs(id,kind,payload,status,created,updated,checkpoint) VALUES('job','transfer','{}','running',0,0,3)")
 reopened=Store(store.path)
 row=reopened.rows('SELECT * FROM jobs')[0]
 assert row['status']=='interrupted' and row['checkpoint']==3

def test_file_metadata_conditional_undo_preserves_other_tags(service,tmp_path):
 identity,media,_=scanned(service,tmp_path)
 p=service.metadata_preview(identity,[1],{'name':'After','genre':'Pop'},'file')
 job=service.commit(p['id']);assert wait(service,job)['status']=='complete'
 undo=service.undo_preview(identity,job)
 assert wait(service,service.commit(undo['id']))['status']=='complete'
 from mutagen.flac import FLAC
 audio=FLAC(media)
 assert audio['title']==['Before'] and audio['genre']==['Trap'] and audio['custom-field']==['Preserve me']

def test_folder_health_reports_orphans_without_touching_files(service,tmp_path):
 identity,media,_=scanned(service,tmp_path)
 orphan=flac(tmp_path/'orphan.flac');(tmp_path/'empty').mkdir()
 report=service.run_job('folder_health',{'profile':identity,'root':str(tmp_path)},'report',lambda *args:None)
 assert [r['path'] for r in report['orphaned']]==[str(orphan)]
 assert str(tmp_path/'empty') in report['empty_folders'] and orphan.exists() and media.exists()

def test_fingerprint_unavailable_is_explicit(service,tmp_path,monkeypatch):
 identity,_,_=scanned(service,tmp_path)
 monkeypatch.setattr('backend.service.shutil.which',lambda name:None)
 with pytest.raises(ValueError,match='Chromaprint'):service.duplicates(identity,'fingerprint')

def test_hash_duplicates_include_same_audio(service,tmp_path):
 identity,_,_=scanned(service,tmp_path)
 groups=service.duplicates(identity,'hash')
 assert groups[0]['ids']==[1,2] and groups[0]['tier']=='exact_hash'

def test_quarantine_requires_supported_media_and_preserves_snapshot(tmp_path):
 app=create_app(tmp_path/'api-quarantine',TOKEN)
 media=flac(tmp_path/'song.flac');source=xml(tmp_path/'Library.xml',media)
 with TestClient(app) as client:
  client.headers['Authorization']='Bearer '+TOKEN
  identity=app.state.service.add_profile('Test',str(source),'xml')
  app.state.service.scan(identity,'scan',lambda *args:None)
  bad=tmp_path/'notes.txt';bad.write_text('do not move')
  assert client.post('/preview/quarantine',json={'profile':identity,'paths':[str(bad)],'destination':str(tmp_path/'quarantine')}).status_code==400
  options=client.post(f'/profiles/{identity}/options',json={'roots':[str(tmp_path)],'exclusions':['skip'],'scan_interval_minutes':30})
  assert options.status_code==200 and options.json()['config']['scan_interval_minutes']==30

def test_disk_space_checked_before_transfer(store,tmp_path,monkeypatch):
 source=tmp_path/'source.mp3';source.write_bytes(b'test')
 monkeypatch.setattr('backend.filesystem.shutil.disk_usage',lambda path:SimpleNamespace(free=0))
 with pytest.raises(ValueError,match='disk space'):verified_transfer(source,tmp_path/'dest.mp3',signature(source),'move',store,'job')
 assert source.exists() and not (tmp_path/'dest.mp3').exists()

def test_cancel_boundary_preserves_completed_transfer(service,tmp_path):
 # A completed transfer is journaled independently of a job checkpoint.
 source=tmp_path/'source.mp3';source.write_bytes(b'test')
 target=tmp_path/'quarantine.mp3'
 identity=verified_transfer(source,target,signature(source),'quarantine',service.store,'interrupted')
 manifest=service.store.rows('SELECT * FROM transfers WHERE id=?',(identity,))[0]
 assert manifest['status']=='complete' and target.exists() and not source.exists()
 restore=service.restore_preview(identity)
 assert wait(service,service.commit(restore['id']))['status']=='complete'
 assert source.read_bytes()==b'test'

def test_live_drm_is_never_edited(store):
 track=SimpleNamespace(Genre='Trap',KindAsString='Protected AAC audio file',Location='song.m4p')
 result=write_tracks(lambda:fake_app(track),[{'pid':'FFFFFFFF80000001','fields':{'genre':'Pop'}}],store,'job')[0]
 assert result['errors'] and track.Genre=='Trap' and not store.rows('SELECT * FROM edits')

def test_optional_com_properties_do_not_block_supported_tag_writes(store):
 class Track:
  Genre='Trap'
  @property
  def KindAsString(self):raise RuntimeError('Optional COM member unavailable')
  @property
  def Location(self):raise RuntimeError('No local file location')
 track=Track()
 result=write_tracks(lambda:fake_app(track),[{'pid':'FFFFFFFF80000001','fields':{'genre':'Pop'}}],store,'job')[0]
 assert not result['errors'] and track.Genre=='Pop'


def test_live_scan_uses_documented_playlist_source_and_persistent_ids():
 from backend.com_service import scan_library
 first=SimpleNamespace(Name='One',Genre='Indie',Location='',Duration=1)
 second=SimpleNamespace(Name='Two',Genre='Jazz',Location='',Duration=2)
 class Tracks:
  Count=2
  def Item(self,index):return [first,second][index-1]
 playlist=SimpleNamespace(Name='Synthetic playlist',Tracks=[second,first])
 app=SimpleNamespace(LibraryPlaylist=SimpleNamespace(Tracks=Tracks(),Source=SimpleNamespace(Playlists=[playlist])),
  ITObjectPersistentIDHigh=lambda track:-1,
  ITObjectPersistentIDLow=lambda track:-2147483648 if track is first else 2)
 result=scan_library(app)
 assert result['tracks']['1']['Persistent ID']=='FFFFFFFF80000000'
 assert result['tracks']['1']['Total Time']==1000
 assert result['playlists']==[{'Name':'Synthetic playlist','Playlist Items':[{'Track ID':2},{'Track ID':1}]}]
