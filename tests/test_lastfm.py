"""Last.fm read-only contracts, using provider-shaped responses without a real account."""
import json
from types import SimpleNamespace
import pytest
import requests
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.lastfm import LastFM, image_url
from backend.store import Store

KEY = 'a' * 32
IMAGE = 'https://lastfm.freetls.fastly.net/i/u/300x300/real-cover.png'
TOKEN = 'fixture-session-token-longer-than-32-characters'

@pytest.fixture
def client(tmp_path):
 app = create_app(tmp_path, TOKEN)
 with TestClient(app, headers={'Authorization': 'Bearer ' + TOKEN}) as c:
  yield c, app.state.service


def response(data, code=200):
 return SimpleNamespace(status_code=code, json=lambda: data, raise_for_status=lambda: None)


def connect_fixture(monkeypatch):
 def request(url, **kw):
  assert url == 'https://ws.audioscrobbler.com/2.0/'
  assert kw['params']['api_key'] == KEY and kw['allow_redirects'] is False
  assert kw['timeout'] == (5,20)
  return response({'user': {'name':'Listener', 'realname':'Music listener', 'playcount':'48000', 'image':[{'size':'large','#text':IMAGE}]}})
 monkeypatch.setattr('backend.lastfm.requests.get', request)


def test_connection_verifies_user_keeps_key_out_of_ui_and_preferences(client, monkeypatch):
 c,s=client;connect_fixture(monkeypatch)
 result=c.post('/lastfm/connect', json={'api_key':KEY,'username':'Listener'})
 assert result.status_code == 200
 assert result.json()['user']['image'] == IMAGE and result.json()['user']['play_count'] == 48000
 assert KEY not in result.text and KEY not in c.get('/lastfm/status').text and KEY not in c.get('/settings').text
 assert s.store.setting('lastfm_connection')['api_key'] == KEY
 assert c.post('/lastfm/disconnect').json()['connected'] is False
 assert s.store.setting('lastfm_connection') == {}
 assert c.get('/lastfm/charts').status_code == 400


@pytest.mark.parametrize('view,root,item', [('recent','recenttracks','track'),('tracks','toptracks','track'),('artists','topartists','artist'),('albums','topalbums','album')])
@pytest.mark.parametrize('period',['overall','7day','1month','3month','6month','12month'])
def test_chart_views_periods_pages_and_cache(client,monkeypatch,view,root,item,period):
 c,s=client;connect_fixture(monkeypatch);c.post('/lastfm/connect',json={'api_key':KEY,'username':'Listener'})
 calls=[]
 def request(url,**kw):
  p=kw['params'];calls.append(p);assert p['method']=={'recent':'user.getRecentTracks','tracks':'user.getTopTracks','artists':'user.getTopArtists','albums':'user.getTopAlbums'}[view]
  assert p['page']==2 and p['limit']==25
  if view!='recent': assert p['period']==period
  else: assert 'period' not in p
  return response({root:{item:[{'name':'Coffee (Live in LA)','artist':{'name':'beabadoobee'},'album':{'#text':'Live in LA'},'playcount':'123','date':{'uts':'1700000000'},'@attr':{'nowplaying':'true'},'image':[{'#text':IMAGE}]}],'@attr':{'totalPages':'4','total':'100'}}})
 monkeypatch.setattr('backend.lastfm.requests.get',request)
 url=f'/lastfm/charts?view={view}&period={period}&page=2'
 result=c.get(url);assert result.status_code==200
 data=result.json();assert data['items'][0]['plays']==123 and data['items'][0]['artist']=='beabadoobee' and data['items'][0]['image']==IMAGE
 assert data['items'][0]['now_playing'] and data['pages']==4
 assert c.get(url).json()==data and len(calls)==1
 c.get(url+'&refresh=true');assert len(calls)==2


def test_bad_login_preserves_valid_connection_and_never_echoes_key(client,monkeypatch):
 c,s=client;connect_fixture(monkeypatch);c.post('/lastfm/connect',json={'api_key':KEY,'username':'Listener'})
 monkeypatch.setattr('backend.lastfm.requests.get',lambda *a,**k:response({'error':10,'message':KEY}))
 r=c.post('/lastfm/connect',json={'api_key':'b'*32,'username':'Other'});assert r.status_code==503 and KEY not in r.text
 assert s.lastfm.status()['user']['name']=='Listener'
 monkeypatch.setattr('backend.lastfm.requests.get',lambda *a,**k:(_ for _ in ()).throw(requests.ConnectionError('private-url?api_key='+KEY)))
 r=c.get('/lastfm/charts');assert r.status_code==503 and KEY not in r.text


@pytest.mark.parametrize('url',['http://lastfm.freetls.fastly.net/a','https://127.0.0.1/a','https://lastfm.freetls.fastly.net.evil/a','https://evil@lastfm.freetls.fastly.net/a','https://lastfm.freetls.fastly.net:444/a','file:///etc/passwd','https://lastfm.freetls.fastly.net/i/u/2a96cbd8b46e442fc41c2b86b821562f.png'])
def test_picture_allowlist_rejects_untrusted_urls(client,monkeypatch,url):
 c,s=client;assert image_url(url)==''
 monkeypatch.setattr('backend.lastfm.requests.get',lambda *a,**k:pytest.fail('Untrusted URL was fetched'))
 assert c.post('/lastfm/image',json={'url':url}).json()=={'image':None}


def test_track_cover_uses_album_picture_and_caches(client,monkeypatch):
 c,s=client;connect_fixture(monkeypatch);c.post('/lastfm/connect',json={'api_key':KEY,'username':'Listener'})
 calls=[]
 def request(url,**kw):
  calls.append(kw);assert kw['params']['method']=='track.getInfo' and kw['params']['track']=='Coffee (Live in LA)' and kw['params']['artist']=='beabadoobee'
  return response({'track':{'album':{'image':[{'#text':IMAGE}]}}})
 monkeypatch.setattr('backend.lastfm.requests.get',request);monkeypatch.setattr(s.lastfm,'image',lambda url:{'image':'data:image/jpeg;base64,fixture'})
 payload={'name':'Coffee (Live in LA)','artist':'beabadoobee'}
 assert c.post('/lastfm/track-image',json=payload).json()['image'].startswith('data:')
 c.post('/lastfm/track-image',json=payload);assert len(calls)==1


def test_picture_download_has_size_limit_and_disallows_redirect(client,monkeypatch):
 c,s=client
 class ImageResponse:
  status_code=200;headers={'Content-Type':'image/jpeg'}
  def __enter__(self):return self
  def __exit__(self,*a):pass
  def iter_content(self,size):yield b'x'*(2*1024*1024+1)
 def request(url,**kw):
  assert url==IMAGE and kw['allow_redirects'] is False and kw['stream'] is True
  return ImageResponse()
 monkeypatch.setattr('backend.lastfm.requests.get',request)
 assert c.post('/lastfm/image',json={'url':IMAGE}).json()=={'image':None}


def test_discovery_removal_persists_and_never_deletes_source_or_profiles(client,tmp_path,monkeypatch):
 c,s=client;path=tmp_path/'Library.xml';path.write_text('unchanged')
 monkeypatch.setattr('backend.api.legacy.default_library_xml_candidates',lambda:[path])
 assert c.get('/discovery').json()['xml'][0]['path']==str(path)
 assert c.post('/discovery/remove',json={'path':str(path)}).status_code==200
 assert c.get('/discovery').json()['xml']==[] and path.read_text()=='unchanged'
 assert Store(s.store.path).setting('discovery_hidden')==[str(path)]
 c.post('/discovery/restore');assert len(c.get('/discovery').json()['xml'])==1


def test_lastfm_endpoints_require_session_token(tmp_path):
 app=create_app(tmp_path,TOKEN)
 with TestClient(app) as c:
  assert c.get('/lastfm/status').status_code==401
  assert c.post('/lastfm/connect',json={'api_key':KEY,'username':'Listener'}).status_code==401


@pytest.mark.parametrize('error,message',[(6,'username'),(10,'API key'),(17,'private'),(26,'suspended'),(29,'too many requests')])
def test_provider_error_messages_are_clear_and_redacted(client,monkeypatch,error,message):
 c,s=client;connect_fixture(monkeypatch);c.post('/lastfm/connect',json={'api_key':KEY,'username':'Listener'})
 monkeypatch.setattr('backend.lastfm.requests.get',lambda *a,**k:response({'error':error,'message':'request?api_key='+KEY}))
 r=c.get('/lastfm/charts');assert r.status_code==503 and message in r.text and KEY not in r.text


def test_invalid_key_body_is_not_echoed_in_validation_error(client):
 c,s=client
 r=c.post('/lastfm/connect',json={'api_key':'private-invalid-key','username':'Listener'})
 assert r.status_code==422 and 'private-invalid-key' not in r.text
 assert s.store.setting('lastfm_connection',{})=={}


def test_bounded_profile_picture_is_a_real_decodable_thumbnail(client,monkeypatch):
 from io import BytesIO
 from PIL import Image
 import base64
 c,s=client;data=BytesIO();Image.new('RGB',(300,300),'purple').save(data,format='PNG')
 class ImageResponse:
  status_code=200;headers={'Content-Type':'image/png'}
  def __enter__(self):return self
  def __exit__(self,*a):pass
  def iter_content(self,size):yield data.getvalue()
 monkeypatch.setattr('backend.lastfm.requests.get',lambda *a,**k:ImageResponse())
 result=c.post('/lastfm/image',json={'url':IMAGE}).json()['image'];assert result.startswith('data:image/jpeg;base64,')
 with Image.open(BytesIO(base64.b64decode(result.split(',',1)[1]))) as picture:assert picture.size==(96,96)
