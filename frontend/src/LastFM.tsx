import React, { useEffect, useRef, useState } from 'react';
import { Music2, UserRound, RefreshCw } from 'lucide-react';
import { api } from './api';

const periods = [
  ['overall', 'All time'], ['7day', 'Last 7 days'], ['1month', 'Last month'],
  ['3month', 'Last 3 months'], ['6month', 'Last 6 months'], ['12month', 'Last year']
];

// Keep picture requests bounded so chart browsing cannot crowd out library requests.
let inFlight = 0;
const waiting: (() => void)[] = [];
async function loadPicture(body: { kind: string; name: string; artist: string; url: string }) {
  await new Promise<void>(resolve => {
    const start = () => { inFlight++; resolve(); };
    if (inFlight < 2) start();
    else waiting.push(start);
  });
  try {
    return await api('/lastfm/picture', 'POST', body);
  } finally {
    inFlight--;
    waiting.shift()?.();
  }
}

const PLACEHOLDER_IDS = ['2a96cbd8b46e442fc41c2b86b821562f', 'c6f59c1e5e7240a4c0d427abd71f3dbb'];

// Display valid public HTTPS URLs from Last.fm directly, as Dashboard does.
// Backend downloads still use a strict CDN allowlist.
function safeLastFMImage(value: string) {
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.toLowerCase().replace(/\.$/, '');
    if (!['http:', 'https:'].includes(parsed.protocol) || !host ||
      host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local') ||
      /^\d{1,3}(?:\.\d{1,3}){3}$/.test(host) || host.includes(':') ||
      parsed.username || parsed.password || !['', '80', '443'].includes(parsed.port) ||
      PLACEHOLDER_IDS.some(id => parsed.href.toLowerCase().includes(id))) return '';
    parsed.protocol = 'https:';
    parsed.port = '';
    parsed.pathname = parsed.pathname.replace(/\/(?:50s|64s|126s|174s|300s|600s|300x300|600x600)\//, '/300x300/');
    return parsed.href;
  } catch {
    return '';
  }
}

function Picture({ url, name, artist = '', album = '', kind, revision }: {
  url: string; name: string; artist?: string; album?: string;
  kind: 'profile' | 'track' | 'album' | 'artist'; revision: number
}) {
  const direct = safeLastFMImage(url);
  const [image, setImage] = useState(direct);
  const [remoteFallback, setRemoteFallback] = useState('');
  const recoveryStarted = useRef(false);

  useEffect(() => {
    let alive = true;
    const fallback = safeLastFMImage(url);
    recoveryStarted.current = false;
    setRemoteFallback('');
    setImage(fallback);
    if (!fallback) {
      recoveryStarted.current = true;
      loadPicture({ url: '', name, artist, kind }).then(result => {
        if (!alive) return;
        const remote = safeLastFMImage(result.url || '');
        setRemoteFallback(remote);
        setImage(result.image || remote);
      }).catch(() => {});
    }
    return () => { alive = false; };
  }, [url, name, artist, album, kind, revision]);

  const recover = () => {
    if (image.startsWith('data:')) {
      setImage(remoteFallback && remoteFallback !== direct ? remoteFallback : '');
      return;
    }
    if (recoveryStarted.current) {
      setImage('');
      return;
    }
    recoveryStarted.current = true;
    setImage('');
    loadPicture({ url: '', name, artist, kind }).then(result => {
      const remote = safeLastFMImage(result.url || '');
      setRemoteFallback(remote && remote !== direct ? remote : '');
      setImage(result.image || (remote && remote !== direct ? remote : ''));
    }).catch(() => {});
  };

  return <div className={kind === 'profile' ? 'lastfm-avatar' : 'lastfm-cover'}>
    {image
      ? <img src={image} onError={recover} alt={kind === 'profile' ? name + "'s profile picture" : 'Artwork for ' + name} />
      : kind === 'profile' || kind === 'artist'
        ? <UserRound size={kind === 'profile' ? 44 : 24} />
        : <Music2 size={24} />}
  </div>;
}

export function LastFM() {
  const [account, setAccount] = useState<any>(null), [key, setKey] = useState(''), [username, setUsername] = useState('');
  const [view, setView] = useState('recent'), [period, setPeriod] = useState('overall'), [page, setPage] = useState(1), [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<any>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false), [connecting, setConnecting] = useState(false);
  const generation = useRef(0);

  useEffect(() => {
    let alive = true;
    api('/lastfm/status').then(result => alive && setAccount((current: any) => current || result))
      .catch(e => alive && setError(e.message));
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    const current = ++generation.current;
    if (!account?.connected) { setData(null); setBusy(false); return; }
    let alive = true;
    setBusy(true); setError(''); setData(null);
    const query = new URLSearchParams({ view, period, page: String(page), refresh: String(refresh > 0) });
    api('/lastfm/charts?' + query).then(result => {
      if (alive && current === generation.current) setData(result);
    }).catch(e => {
      if (alive && current === generation.current) setError(e.message);
    }).finally(() => {
      if (alive && current === generation.current) setBusy(false);
    });
    return () => { alive = false; };
  }, [account, view, period, page, refresh]);

  async function connect(e: React.FormEvent) {
    e.preventDefault(); setConnecting(true); setError('');
    try {
      setAccount(await api('/lastfm/connect', 'POST', { api_key: key.trim(), username: username.trim() }));
      setKey(''); setPage(1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setConnecting(false); }
  }

  async function disconnect() {
    setConnecting(true); setError('');
    try {
      setAccount(await api('/lastfm/disconnect', 'POST')); setKey(''); setData(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setConnecting(false); }
  }

  return <div className="lastfm-page">
    {error && <div className="banner error" role="alert">{error}</div>}
    <div className="card">
      {account?.connected
        ? <div className="lastfm-profile">
            <Picture kind="profile" url={account.user.image || ''} name={account.user.name} revision={refresh} />
            <div><h2>{account.user.display_name}</h2><p>@{account.user.name}</p>
              <small>{account.user.play_count.toLocaleString()} plays on Last.fm{account.user.country && ' · ' + account.user.country}</small>
            </div>
            <button disabled={connecting} title="🔌 Remove the saved API key from this app. Your Last.fm account and listening history stay." onClick={disconnect}>Disconnect</button>
          </div>
        : <>
            <h2>🎧 Connect Last.fm</h2><p>Your listening history, recent songs and favourites in one place.</p>
            <form className="lastfm-connect" onSubmit={connect}>
              <label>Last.fm username<input aria-label="Last.fm username" autoComplete="username" maxLength={128} value={username} onChange={e => setUsername(e.target.value)} required /></label>
              <label>API key<input aria-label="Last.fm API key" type="password" autoComplete="off" maxLength={32} value={key} onChange={e => setKey(e.target.value)} required /></label>
              <button className="primary" disabled={connecting || !username.trim() || key.trim().length !== 32}>{connecting ? 'Connecting…' : 'Connect Last.fm'}</button>
            </form>
            <button onClick={() => window.libraryManager?.lastfmKey().catch(e => setError(e.message))}>Get a Last.fm API key ↗</button>
            <p className="footnote">🔑 Use your own Last.fm API key and username. This reads public listening data; it does not sign in to the website or send scrobbles. The key is saved locally and removed when you disconnect.</p>
          </>}
    </div>

    {account?.connected && <div className="card">
      <div className="lastfm-tools">
        <label>Show<select aria-label="Last.fm listening view" value={view} onChange={e => { setView(e.target.value); setPage(1); }}>
          <option value="recent">Recently played</option><option value="tracks">Top songs</option><option value="artists">Top artists</option><option value="albums">Top albums</option>
        </select></label>
        {view !== 'recent' && <label>Time period<select aria-label="Last.fm time period" value={period} onChange={e => { setPeriod(e.target.value); setPage(1); }}>
          {periods.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
        </select></label>}
        <button disabled={busy} onClick={() => setRefresh(r => r + 1)}><RefreshCw size={16} />Refresh</button>
      </div>
      {busy && <p role="status">Loading Last.fm listening history…</p>}
      {data && !busy && <>
        <div className="lastfm-list">
          {data.items.map((song: any, i: number) => <div className="lastfm-row" key={[page, view, song.name, i].join('-')}>
            <span className="muted">{(page - 1) * 25 + i + 1}</span>
            <Picture url={song.image || ''} name={song.name} artist={song.artist} album={song.album || ''} kind={view === 'artists' ? 'artist' : view === 'albums' ? 'album' : 'track'} revision={refresh} />
            <div><b>{song.name}</b>{song.artist && <small>{song.artist}{song.album && ' · ' + song.album}</small>}</div>
            <span className="lastfm-count">{view === 'recent'
              ? (song.now_playing ? '🎵 Playing now' : song.timestamp ? new Date(song.timestamp * 1000).toLocaleString() : 'Recently played')
              : song.plays.toLocaleString() + ' plays'}</span>
          </div>)}
        </div>
        {!data.items.length && <p className="empty">No listening history in this view yet.</p>}
        <div className="table-footer"><span>Page {page} of {data.pages.toLocaleString()}</span><div>
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button>
          <button disabled={page >= data.pages} onClick={() => setPage(p => p + 1)}>Next</button>
        </div></div>
      </>}
      <p className="footnote">🖼️ Covers and artist photos appear when Last.fm supplies them. Some artists have no photo available. Recent plays are refreshed when you open this tab or press Refresh.</p>
    </div>}
  </div>;
}
