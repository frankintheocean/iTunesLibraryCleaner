"""Scan timing uses real throughput rather than an unrelated short task."""
import threading
from backend.store import Store
from backend.jobs import Jobs


def timing(tmp_path,elapsed):
 store=Store(tmp_path/'manager.sqlite');jobs=Jobs.__new__(Jobs);jobs.store=store;jobs.stop=threading.Event()
 store.execute("INSERT INTO jobs(id,kind,status,elapsed,progress,eta_end) VALUES('scan','scan','running',?,0,NULL)",(elapsed,))
 return store,jobs


def test_large_scan_estimate_is_not_capped_at_two_minutes(tmp_path):
 store,jobs=timing(tmp_path,10)
 jobs.checkpoint('scan',100,48000,'Reading iTunes songs')
 row=store.rows("SELECT eta_end FROM jobs WHERE id='scan'")[0]
 assert row['eta_end']==4800
 store.execute("UPDATE jobs SET elapsed=20 WHERE id='scan'")
 jobs.checkpoint('scan',250,48000,'Reading iTunes songs')
 next_end=store.rows("SELECT eta_end FROM jobs WHERE id='scan'")[0]['eta_end']
 assert next_end<=row['eta_end'] and next_end-20<row['eta_end']-10


def test_scan_warmup_does_not_show_a_premature_fast_estimate(tmp_path):
 store,jobs=timing(tmp_path,1)
 jobs.checkpoint('scan',100,48000,'Reading iTunes songs')
 assert store.rows("SELECT eta_end FROM jobs WHERE id='scan'")[0]['eta_end'] is None


def test_saving_phase_does_not_replace_read_estimate_with_tiny_percentage(tmp_path):
 store,jobs=timing(tmp_path,100)
 store.execute("UPDATE jobs SET eta_end=1000 WHERE id='scan'")
 jobs.checkpoint('scan',98,100,'Saving and indexing the library')
 assert store.rows("SELECT eta_end FROM jobs WHERE id='scan'")[0]['eta_end']==1000


def test_a_completed_tiny_scan_does_not_seed_another_scan(tmp_path):
 store=Store(tmp_path/'manager.sqlite')
 store.execute("INSERT INTO jobs(id,kind,status,elapsed,created) VALUES('old','scan','complete',.1,1)")
 inspected=threading.Event();release=threading.Event();initial=[]
 def handler(kind,payload,identity,progress):
  initial.append(store.rows('SELECT eta_end FROM jobs WHERE id=?',(identity,))[0]['eta_end']);inspected.set();release.wait(3);return {}
 jobs=Jobs(store,handler)
 try:
  jobs.enqueue('scan',{'profile':'large'})
  assert inspected.wait(3) and initial==[None]
 finally:release.set();jobs.close()
