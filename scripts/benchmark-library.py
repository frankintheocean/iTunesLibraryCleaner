"""Time real parsing, indexing, searches and a file edit on generated data."""
import argparse
import gc
import json
import plistlib
import subprocess
import sys
import tempfile
import time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from backend.service import Service
from backend import metadata


def run(service_class, folder, count):
    folder.mkdir(parents=True,exist_ok=True)
    # Valid metadata-only FLAC fixture; no personal files or iTunes writes.
    bits=(44100<<44)|(1<<41)|(15<<36)|44100
    stream=b'\x10\x00\x10\x00'+b'\x00'*6+bits.to_bytes(8,'big')+b'\x00'*16
    media=folder/'song.flac';media.write_bytes(b'fLaC'+b'\x80\x00\x00\x22'+stream)
    from mutagen.flac import FLAC
    audio=FLAC(media);audio['title']='Before';audio['artist']='Artist';audio['genre']='Indie';audio.save()
    tracks={str(i):{'Track ID':i,'Persistent ID':f'{i:016X}','Name':f'Song {i:05d}','Artist':f'Artist {i%100}','Album':f'Album {i%1000}','Genre':'Indie','Size':1048576} for i in range(1,count+1)}
    tracks['1'].update({'Name':'Before','Location':media.as_uri()})
    tracks[str(count//2)]['Name']='Coffee (Live in LA)'
    source=folder/'Library.xml';source.write_bytes(plistlib.dumps({'Tracks':tracks,'Playlists':[]}))
    service=service_class(folder/'state');identity=service.add_profile('Generated benchmark',str(source),'xml')
    def timed(work):
        start=time.perf_counter();value=work();return value,round(time.perf_counter()-start,6)
    try:
        result,scan=timed(lambda:service.scan(identity,'benchmark',lambda *args:None))
        assert result['tracks']==count
        stats,overview=timed(lambda:service.overview(identity));assert stats['tracks']==count
        _,warm_overview=timed(lambda:service.overview(identity))
        searches=[]
        for query in ('Coffee','song 100','Artist 42','Album 123'):
            matches,seconds=timed(lambda:service.tracks(identity,query));searches.append({'query':query,'seconds':seconds,'matches':matches['total']})
        assert searches[0]['matches']==1
        preview,preview_time=timed(lambda:service.metadata_preview(identity,[1],{'name':'After'},'file'))
        # Exercise the same real handler as a queued edit; fake job IDs only omit queue timing.
        _,edit=timed(lambda:service.run_job('metadata',{'profile':identity,**preview},'benchmark-edit',lambda *args:None))
        assert metadata.inspect(media)['tags']['name']==['After']
        assert service.tracks(identity,'After')['total']==1
        return {'tracks':count,'xml_bytes':source.stat().st_size,'scan_seconds':scan,'overview_seconds':overview,'cached_overview_seconds':warm_overview,'searches':searches,'preview_seconds':preview_time,'one_file_title_edit_seconds':edit}
    finally:
        service.jobs.close();service.scheduler.join(5)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--tracks',type=int,default=40000);parser.add_argument('--compare-v2',action='store_true');parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    if args.tracks<100:parser.error('Use at least 100 tracks.')
    with tempfile.TemporaryDirectory(prefix='itunes-speed-') as temp:
        report={'fixture':'Generated XML and one metadata-only FLAC; not live COM or a personal library.','v3':run(Service,Path(temp)/'v3',args.tracks)}
        if args.compare_v2:
            code=subprocess.check_output(['git','show','v2.0.0:backend/service.py'],cwd=root,text=True)
            namespace={'__name__':'backend.benchmark_baseline','__package__':'backend'};exec(compile(code,'v2-service.py','exec'),namespace)
            store_code=subprocess.check_output(['git','show','v2.0.0:backend/store.py'],cwd=root,text=True)
            store_namespace={'__name__':'backend.benchmark_store','__package__':'backend'};exec(compile(store_code,'v2-store.py','exec'),store_namespace)
            namespace['Store']=store_namespace['Store']
            report['v2']=run(namespace['Service'],Path(temp)/'v2',args.tracks)
            # Release the old version's cyclic connection objects after timing its work.
            gc.collect()
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
