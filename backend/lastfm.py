"""Read a Last.fm profile and listening charts. Never scrobble or change an account."""
from __future__ import annotations
import re
import threading
import time
from urllib.parse import urlsplit, urljoin, urlunsplit, quote
from html.parser import HTMLParser
import requests
from .artwork import encode_thumbnail

PERIODS = {'overall', '7day', '1month', '3month', '6month', '12month'}
VIEWS = {'recent': ('user.getRecentTracks', 'recenttracks', 'track'),
         'tracks': ('user.getTopTracks', 'toptracks', 'track'),
         'artists': ('user.getTopArtists', 'topartists', 'artist'),
         'albums': ('user.getTopAlbums', 'topalbums', 'album')}
IMAGE_HOSTS = {'lastfm.freetls.fastly.net', 'lastfm-img2.akamaized.net', 'userserve-ak.last.fm'}
PLACEHOLDERS = ('2a96cbd8b46e442fc41c2b86b821562f', 'c6f59c1e5e7240a4c0d427abd71f3dbb')


def image_url(value):
    if not isinstance(value, str) or len(value) > 2048: return ''
    try:
        url = urlsplit(value)
        if url.scheme not in ('http', 'https') or url.hostname not in IMAGE_HOSTS or url.port not in (None, 443) or url.username or url.password: return ''
        if any(p in value for p in PLACEHOLDERS): return ''
        return urlunsplit(('https', url.netloc, url.path, url.query, ''))
    except ValueError: return ''


def picture(raw):
    images = raw.get('image', [])
    if not isinstance(images, list): return ''
    return next((image_url(item.get('#text')) for item in reversed(images) if isinstance(item, dict) and image_url(item.get('#text'))), '')


class LastFM:
    def __init__(self, store):
        self.store = store
        self._cache = {}; self._images = {}; self._track_images = {}; self._pictures = {}; self._lock = threading.RLock()
        self._rate_lock = threading.Lock(); self._next_request = 0

    def _request(self, method, key, username, **options):
        with self._rate_lock:
            wait = self._next_request - time.monotonic()
            if wait > 0: time.sleep(wait)
            self._next_request = time.monotonic() + .25
        try:
            response = requests.get('https://ws.audioscrobbler.com/2.0/', params={
                'method': method, 'api_key': key, 'user': username, 'format': 'json', **options},
                timeout=(5, 20), allow_redirects=False)
            if response.status_code == 429:
                raise RuntimeError('Last.fm is receiving too many requests. Wait a moment, then refresh.')
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            # Request exceptions can include the API key in their URL.
            raise RuntimeError('Last.fm could not be reached. Check your connection and try again.') from None
        if not isinstance(data, dict): raise RuntimeError('Last.fm sent an unreadable response. Try refreshing.')
        if data.get('error'):
            code = str(data['error'])
            messages = {'6': 'Last.fm could not find that username.', '10': 'Last.fm did not accept this API key.',
                        '26': 'This Last.fm API key has been suspended.', '17': 'This user’s listening history is private.',
                        '29': 'Last.fm is receiving too many requests. Wait a moment, then refresh.'}
            raise RuntimeError(messages.get(code, 'Last.fm could not load this view. Try again later.'))
        return data

    def status(self):
        conf = self.store.setting('lastfm_connection', {})
        return {'connected': bool(conf.get('api_key')), 'user': conf.get('user')}

    def connect(self, api_key, username):
        if not re.fullmatch(r'[0-9a-fA-F]{32}', api_key): raise ValueError('Enter your 32-character Last.fm API key.')
        if not username.strip() or len(username) > 128 or any(ord(c) < 32 for c in username): raise ValueError('Enter your Last.fm username.')
        raw = self._request('user.getInfo', api_key, username.strip()).get('user')
        if not isinstance(raw, dict) or not raw.get('name'): raise RuntimeError('Last.fm did not return a user profile.')
        user = {'name': str(raw['name']), 'display_name': str(raw.get('realname') or raw['name']),
                'image': picture(raw), 'play_count': self._number(raw.get('playcount')), 'country': str(raw.get('country') or '')}
        with self._lock:
            self.store.set_setting('lastfm_connection', {'api_key': api_key, 'username': user['name'], 'user': user})
            self._cache.clear()
        return {'connected': True, 'user': user}

    def disconnect(self):
        with self._lock:
            self.store.set_setting('lastfm_connection', {})
            self._cache.clear(); self._images.clear(); self._track_images.clear(); self._pictures.clear()
        return {'connected': False, 'user': None}

    @staticmethod
    def _number(value):
        try: return max(0, int(value))
        except (ValueError, TypeError): return 0

    def charts(self, view, period='overall', page=1, refresh=False):
        if view not in VIEWS or period not in PERIODS or not 1 <= page <= 10000: raise ValueError('Choose a valid listening view, time period and page.')
        conf = self.store.setting('lastfm_connection', {})
        if not conf.get('api_key'): raise ValueError('Connect a Last.fm API key and username first.')
        key = (conf['username'], conf['api_key'], view, period, page)
        with self._lock:
            cached = self._cache.get(key)
            if cached and not refresh and time.monotonic() - cached[0] < 60: return cached[1]
        method, root, item = VIEWS[view]
        options = {'page': page, 'limit': 25}
        if view != 'recent': options['period'] = period
        raw = self._request(method, conf['api_key'], conf['username'], **options).get(root)
        if not isinstance(raw, dict): raise RuntimeError('Last.fm sent an unreadable listening chart.')
        entries = raw.get(item) or []
        if isinstance(entries, dict): entries = [entries]
        if not isinstance(entries, list): raise RuntimeError('Last.fm sent an unreadable listening chart.')
        rows = []
        for entry in entries:
            if not isinstance(entry, dict): continue
            artist = entry.get('artist') or {}
            if isinstance(artist, dict): artist = artist.get('name') or artist.get('#text') or ''
            album = entry.get('album') or {}
            if isinstance(album, dict): album = album.get('#text') or album.get('name') or ''
            stamp = entry.get('date') or {}
            rows.append({'name': str(entry.get('name') or 'Untitled'), 'artist': str(artist), 'album': str(album),
                         'image': picture(entry), 'plays': self._number(entry.get('playcount')),
                         'now_playing': (entry.get('@attr') or {}).get('nowplaying') == 'true',
                         'timestamp': self._number(stamp.get('uts'))})
        attr = raw.get('@attr') or {}
        result = {'items': rows, 'page': page, 'pages': max(1, self._number(attr.get('totalPages'))),
                  'total': self._number(attr.get('total')), 'view': view, 'period': period}
        with self._lock:
            if len(self._cache) >= 64: self._cache.pop(next(iter(self._cache)))
            if self.store.setting('lastfm_connection', {}).get('api_key') == conf['api_key']: self._cache[key] = (time.monotonic(), result)
        return result

    def track_image(self, name, artist):
        conf = self.store.setting('lastfm_connection', {})
        if not conf.get('api_key'): return {'image': None}
        identity = (conf['username'], name, artist)
        with self._lock:
            if identity in self._track_images: return {'image': self._track_images[identity]}
        try:
            raw = self._request('track.getInfo', conf['api_key'], conf['username'], track=name, artist=artist)
            album = (raw.get('track') or {}).get('album') or {}
            image = self.image(picture(album))['image']
        except RuntimeError: image = None
        with self._lock:
            if len(self._track_images) >= 256: self._track_images.pop(next(iter(self._track_images)))
            if image: self._track_images[identity] = image
        return {'image': image}

    def _download(self, url, image=True):
        """Bound every redirect and byte count, including old CDN links."""
        def accepted(value):
            if image: return image_url(value)
            try:
                parsed = urlsplit(value)
                if parsed.scheme == 'https' and parsed.hostname in ('www.last.fm', 'last.fm') and not parsed.username and not parsed.password and parsed.port in (None, 443):
                    return value
            except ValueError: pass
            return ''
        url = accepted(url)
        if not url: return None
        try:
            for _ in range(4):
                with requests.get(url, timeout=(5, 15), stream=True, allow_redirects=False,
                                  headers={'User-Agent': 'iTunesManager/3.1.1', 'Accept': 'image/*' if image else 'text/html'}) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        url = accepted(urljoin(url, response.headers.get('Location', '')))
                        if not url: return None
                        continue
                    if response.status_code != 200: return None
                    # Some image CDNs send valid image bytes as application/octet-stream.
                    # The decoder, not a guessed MIME type, decides whether they are pictures.
                    data = bytearray()
                    for chunk in response.iter_content(65536):
                        data.extend(chunk)
                        if len(data) > 2 * 1024 * 1024: return None
                    return bytes(data)
        except requests.RequestException: pass
        return None

    def _page_picture(self, path):
        data = self._download('https://www.last.fm/' + path, image=False)
        if not data: return ''
        class Pictures(HTMLParser):
            def __init__(self): super().__init__(); self.urls = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'meta' and (attrs.get('property') or attrs.get('name')) in ('og:image', 'twitter:image'):
                    url = image_url(attrs.get('content'))
                    if url: self.urls.append(url)
        parser = Pictures()
        parser.feed(data.decode('utf-8', errors='replace'))
        return next(iter(parser.urls), '')

    def resolve_picture(self, kind, name, artist='', url=''):
        if kind not in ('profile', 'track', 'album', 'artist'): raise ValueError('Choose a supported picture type.')
        conf = self.store.setting('lastfm_connection', {})
        if not conf.get('api_key'): return {'image': None}
        identity = (conf['username'], kind, name, artist, url)
        with self._lock:
            cached = self._pictures.get(identity)
            if cached and time.monotonic() - cached[0] < 600: return {'image': cached[1]}
        size = 256 if kind == 'profile' else 96
        result = self.image(url, size)['image'] if image_url(url) else None
        if not result:
            candidate = ''; path = ''
            try:
                if kind == 'profile':
                    raw = self._request('user.getInfo', conf['api_key'], conf['username']).get('user') or {}
                    candidate = picture(raw); path = 'user/' + quote(conf['username'], safe='')
                elif kind == 'artist':
                    # Last.fm's artist API commonly returns a placeholder. The public
                    # artist page still supplies its actual photo through Open Graph.
                    path = 'music/' + quote(name, safe='')
                elif kind == 'album' and artist:
                    raw = self._request('album.getInfo', conf['api_key'], conf['username'], album=name, artist=artist).get('album') or {}
                    candidate = picture(raw); path = 'music/' + quote(artist, safe='') + '/' + quote(name, safe='')
                elif kind == 'track' and artist:
                    raw = self._request('track.getInfo', conf['api_key'], conf['username'], track=name, artist=artist).get('track') or {}
                    album = raw.get('album') or {}; candidate = picture(album)
                    if not candidate and album.get('title'):
                        info = self._request('album.getInfo', conf['api_key'], conf['username'], album=album['title'], artist=artist).get('album') or {}
                        candidate = picture(info)
                    path = 'music/' + quote(artist, safe='') + '/_/' + quote(name, safe='')
            except RuntimeError:
                if kind == 'profile': path = 'user/' + quote(conf['username'], safe='')
                elif artist: path = 'music/' + quote(artist, safe='') + ('/_/' if kind == 'track' else '/') + quote(name, safe='')
            if candidate: result = self.image(candidate, size)['image']
            if not result and path:
                candidate = self._page_picture(path)
                if candidate: result = self.image(candidate, size)['image']
        with self._lock:
            if len(self._pictures) >= 256: self._pictures.pop(next(iter(self._pictures)))
            if result: self._pictures[identity] = (time.monotonic(), result)
        return {'image': result}

    def image(self, url, size=96):
        url = image_url(url)
        if not url: return {'image': None}
        identity = (url, size)
        with self._lock:
            if identity in self._images: return {'image': self._images[identity]}
        data = self._download(url)
        image = encode_thumbnail(data, size) if data else None
        with self._lock:
            if len(self._images) >= 256: self._images.pop(next(iter(self._images)))
            if image: self._images[identity] = image
        return {'image': image}
