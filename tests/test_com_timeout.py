"""Simulate COM worker timing without waiting or requiring Windows/iTunes."""
from types import SimpleNamespace
import pytest
from backend import com_service


def worker(monkeypatch, messages):
 clock=[0.0];messages=list(messages);state={'closed':False,'terminated':False}
 class Pipe:
  def poll(self,wait):
   if messages and clock[0]+wait>=messages[0][0]:clock[0]=messages[0][0];return True
   clock[0]+=wait;return False
  def recv(self):
   value=messages.pop(0)[1]
   if isinstance(value, Exception):raise value
   return value
  def close(self):state['closed']=True
 class Process:
  def start(self):pass
  def join(self,wait):pass
  def is_alive(self):return True
  def terminate(self):state['terminated']=True
 pipe=Pipe()
 context=SimpleNamespace(Pipe=lambda **kw:(pipe,SimpleNamespace(close=lambda:None)),Process=lambda **kw:Process())
 monkeypatch.setattr(com_service.sys,'platform','win32')
 monkeypatch.setattr(com_service.multiprocessing,'get_context',lambda mode:context)
 monkeypatch.setattr(com_service.time,'monotonic',lambda:clock[0])
 return state,clock


def test_large_scan_continues_past_original_deadline(monkeypatch):
 state,clock=worker(monkeypatch,[(0,{'progress':[0,48001,'Reading']}),(800,{'progress':[10000,48001,'Reading']}),(1600,{'progress':[30000,48001,'Reading']}),(2000,{'result':{'tracks':48000}})])
 assert com_service.run_com({'operation':'scan'},'db',timeout=900)['tracks']==48000
 assert clock[0]==2000 and state['closed'] and state['terminated']


def test_write_deadline_is_not_extended_by_progress(monkeypatch):
 state,clock=worker(monkeypatch,[(0,{'progress':[0,3,'Editing']}),(800,{'progress':[1,3,'Editing']}),(1000,{'result':{}})])
 with pytest.raises(TimeoutError,match='uncertain outcome'):com_service.run_com({'operation':'edit'},'db',timeout=900)
 assert clock[0]==900 and state['terminated']


def test_stalled_scan_is_read_only_and_preserves_previous_copy(monkeypatch):
 state,clock=worker(monkeypatch,[(0,{'progress':[0,48000,'Reading']}),(800,{'progress':[0,48000,'Still reading']})])
 with pytest.raises(TimeoutError,match='No live metadata was changed'):com_service.run_com({'operation':'scan'},'db',timeout=900)
 assert clock[0]==900


def test_healthy_scan_has_finite_hard_limit(monkeypatch):
 state,clock=worker(monkeypatch,[(0,{'progress':[0,3,'Reading']}),(800,{'progress':[1,3,'Reading']}),(1600,{'result':{}})])
 with pytest.raises(TimeoutError,match='time limit'):com_service.run_com({'operation':'scan'},'db',timeout=900,max_timeout=1000)
 assert clock[0]==1000


def test_scan_cancel_callback_closes_worker_without_publishing(monkeypatch):
 from backend.jobs import Cancelled
 state,clock=worker(monkeypatch,[(0,{'progress':[0,48000,'Reading']})])
 def progress(*values):
  if clock[0]>=2:raise Cancelled('Cancelled')
 with pytest.raises(Cancelled):com_service.run_com({'operation':'scan'},'db',timeout=900,progress=progress)
 assert state['closed'] and state['terminated']


def test_status_timeout_does_not_warn_about_writes(monkeypatch):
 worker(monkeypatch,[])
 with pytest.raises(TimeoutError,match='refresh the connection') as error:com_service.run_com({'operation':'status'},'db',timeout=15)
 assert 'writes' not in str(error.value)


def test_real_reader_keeps_all_48000_track_ids_and_reports_progress():
 class Track:
  Name='Song';Artist='Artist';Album='Album';Genre='Pop';Location='';Duration=1;Size=10
  def __init__(self,n):self.TrackDatabaseID=n
 class Tracks:
  Count=48000
  def __iter__(self):return (Track(i) for i in range(1,self.Count+1))
 library=SimpleNamespace(Tracks=Tracks(),Source=SimpleNamespace(Playlists=[]))
 app=SimpleNamespace(LibraryPlaylist=library,ITObjectPersistentIDHigh=lambda _:0,
                     ITObjectPersistentIDLow=lambda track:getattr(track,'TrackDatabaseID',0))
 progress=[]
 result=com_service.scan_library(app,lambda done,total,text:progress.append(done))
 assert len(result['tracks'])==48000
 assert result['tracks']['48000']['Persistent ID']=='000000000000BB80'
 assert progress[0]==0 and progress[-1]==48000 and len(progress)==481


def test_scan_can_cancel_before_first_worker_progress(monkeypatch):
 from backend.jobs import Cancelled
 state,clock=worker(monkeypatch,[])
 def cancel(*values):raise Cancelled('Cancelled')
 with pytest.raises(Cancelled):com_service.run_com({'operation':'scan'},'db',timeout=900,progress=cancel)
 assert clock[0]<3 and state['terminated']


def test_scan_worker_exit_has_read_only_error(monkeypatch):
 state,clock=worker(monkeypatch,[(1,EOFError())])
 with pytest.raises(RuntimeError,match='No live metadata was changed'):com_service.run_com({'operation':'scan'},'db',timeout=900)
 assert state['closed']
