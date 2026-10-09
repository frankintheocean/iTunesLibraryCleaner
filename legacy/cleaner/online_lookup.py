"""Fast online metadata helpers used by LibraryCleaner.

Genre lookup sources are pluggable: GenreProvider is a small abstract
interface (`lookup(session, artist, title) -> str`) and ITunesProvider /
LastFmProvider are the two built-in implementations. OnlineLookup stays
the facade cleanup_engine.py and gui.py talk to - its public methods and
constructor signature are unchanged - it just delegates genre lookups to
a provider chain instead of hard-coding the two calls inline. To add a
new source, subclass GenreProvider and pass an instance (or add it to
OnlineLookup.providers after construction); no changes to
cleanup_engine.py are required.
"""
import time
from abc import ABC, abstractmethod

import requests

TIMEOUT_SECS = 1.5
USER_AGENT = "LibraryCleaner/3.6"

# Last.fm calls get a couple of quick retries with a short backoff for
# transient failures (timeouts, connection resets, 5xx) - a single flaky
# request no longer costs the track its genre lookup outright.
#
# The backoff sleep runs on whichever ThreadPoolExecutor worker is doing
# the lookup (max_workers=4 in cleanup_engine.py), so it's real thread
# time taken away from other queued lookups, not just latency on this
# one track. LASTFM_RETRY_BACKOFF_CAP bounds the *total* time a single
# track's lookup can spend sleeping on backoff, so a worker can't be
# tied up for longer than that even if every retry hits a transient
# failure - worth having as the library size (and therefore the number
# of tracks competing for those 4 slots) grows.
LASTFM_RETRY_ATTEMPTS = 3
LASTFM_RETRY_BACKOFF_BASE = 0.4  # seconds; doubles each retry (0.4, 0.8)
LASTFM_RETRY_BACKOFF_CAP = 1.2  # seconds; ceiling on total backoff sleep per lookup
LASTFM_RETRY_STATUS = {500, 502, 503, 504, 429}

# iTunes Search is the primary/first source in the default order and
# already has a Last.fm fallback right after it, so it only gets one
# quick retry (not Last.fm's fuller backoff schedule) - just enough to
# ride out a single transient blip (timeout, connection reset, 5xx/429)
# without adding meaningful latency to every blank-genre lookup.
ITUNES_RETRY_ATTEMPTS = 2
ITUNES_RETRY_BACKOFF_BASE = 0.3  # seconds; single short pause before the retry
ITUNES_RETRY_STATUS = {500, 502, 503, 504, 429}

_FOREIGN_MARKERS = (
    " el ", " la ", " los ", " las ", " del ", " de ", " que ", " para ",
    " nao ", " não ", " voce ", " você ", " der ", " die ", " das ", " und ",
    " nicht ", " ist ", " te ", " aroha ", " whanau ", " whānau ", " aiga ",
    " le ", " les ", " des ", " une ", " un ", " avec ", " dans ",
)


def looks_possibly_foreign(s: str, is_artist_field: bool = False) -> bool:
    if not s:
        return False
    if any(ord(c) > 127 for c in s):
        return True
    lower = f" {s.lower()} "
    return any(marker in lower for marker in _FOREIGN_MARKERS)


class GenreProvider(ABC):
    """Abstract interface for an online genre-lookup source.

    Subclass this and implement `name` and `lookup()` to add a new
    source beyond the built-in iTunes/Last.fm providers. `lookup()`
    should return "" (not raise) for "no result" - both a clean miss
    and a non-transient error are the same "nothing found here, try
    the next provider" outcome from OnlineLookup's point of view.
    Transient failures (timeouts, 5xx/429) should be retried internally
    by the provider, since retry policy (attempt count, backoff) is
    naturally source-specific.
    """

    #: Short identifier used in logs/UI, e.g. "itunes", "lastfm".
    name = "provider"

    @abstractmethod
    def lookup(self, session: requests.Session, artist: str, title: str) -> str:
        """Return a genre string for (artist, title), or "" if none
        was found. Must not raise - network/parsing errors should be
        caught internally and treated as a miss."""
        raise NotImplementedError


class ITunesProvider(GenreProvider):
    """Looks up genre via the public iTunes Search API."""
    name = "itunes"

    def lookup(self, session: requests.Session, artist: str, title: str) -> str:
        for attempt in range(ITUNES_RETRY_ATTEMPTS):
            try:
                resp = session.get(
                    "https://itunes.apple.com/search",
                    params={"media": "music", "entity": "song", "limit": 1,
                            "term": f"{artist} {title}"},
                    timeout=TIMEOUT_SECS,
                )
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    if results:
                        return str(results[0].get("primaryGenreName", "")).strip()
                    return ""  # 200 with no results is a real "no match", not a failure
                if resp.status_code not in ITUNES_RETRY_STATUS:
                    return ""  # non-transient error (e.g. bad request) - retrying won't help
            except (requests.RequestException, ValueError, TypeError):
                pass
            if attempt < ITUNES_RETRY_ATTEMPTS - 1:
                time.sleep(ITUNES_RETRY_BACKOFF_BASE)
        return ""


class LastFmProvider(GenreProvider):
    """Looks up genre via Last.fm's track.gettoptags."""
    name = "lastfm"

    def __init__(self, lastfm_key=""):
        self.lastfm_key = lastfm_key

    def lookup(self, session: requests.Session, artist: str, title: str) -> str:
        effective_key = self.lastfm_key
        if not effective_key:
            return ""
        slept = 0.0
        for attempt in range(LASTFM_RETRY_ATTEMPTS):
            try:
                resp = session.get(
                    "https://ws.audioscrobbler.com/2.0/",
                    params={"method": "track.gettoptags", "artist": artist,
                            "track": title, "api_key": effective_key, "format": "json"},
                    timeout=TIMEOUT_SECS,
                )
                if resp.status_code == 200:
                    tags = resp.json().get("toptags", {}).get("tag", [])
                    if isinstance(tags, dict):
                        tags = [tags]
                    if tags:
                        return str(tags[0].get("name", "")).strip()
                    return ""  # 200 with no tags is a real "no result", not a failure
                if resp.status_code not in LASTFM_RETRY_STATUS:
                    return ""  # non-transient error (e.g. bad key) - retrying won't help
            except (requests.RequestException, ValueError, TypeError):
                pass
            if attempt < LASTFM_RETRY_ATTEMPTS - 1:
                # Cap total backoff sleep for this lookup rather than
                # letting the doubling schedule run unbounded - caps how
                # long a single track can occupy a lookup-executor slot
                # on nothing but backoff (see LASTFM_RETRY_BACKOFF_CAP).
                remaining_budget = LASTFM_RETRY_BACKOFF_CAP - slept
                if remaining_budget <= 0:
                    break
                delay = min(LASTFM_RETRY_BACKOFF_BASE * (2 ** attempt), remaining_budget)
                time.sleep(delay)
                slept += delay
        return ""


class OnlineLookup:
    def __init__(self, lastfm_user="", lastfm_key="", prefer_lastfm=False, providers=None):
        """providers: optional ordered list of GenreProvider instances to
        try (first non-empty result wins), overriding the default
        iTunes/Last.fm order. When omitted, the default two-provider
        chain is built from lastfm_key/prefer_lastfm exactly as before."""
        self.lastfm_user = lastfm_user
        self.lastfm_key = lastfm_key
        self.prefer_lastfm = prefer_lastfm
        self.lang_cache = {}
        self.genre_cache = {}
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

        if providers is not None:
            self.providers = list(providers)
        else:
            itunes = ITunesProvider()
            lastfm = LastFmProvider(lastfm_key=lastfm_key)
            self.providers = [lastfm, itunes] if prefer_lastfm else [itunes, lastfm]

    def is_foreign_language(self, artist: str, title: str) -> bool:
        """Detect the language of the artist/title together in ONE request.

        The previous implementation could make a network request for the
        title and then another for every artist name. Combining them cuts the
        worst-case language-detection traffic roughly in half while retaining
        artist-name detection.
        """
        artist = (artist or "").strip()
        title = (title or "").strip()
        if not artist and not title:
            return False

        cache_key = f"{artist.lower()}|{title.lower()}"
        cached = self.lang_cache.get(cache_key)
        if cached is not None:
            return cached

        combined = f"{artist} - {title}".strip(" -")
        if not looks_possibly_foreign(combined):
            self.lang_cache[cache_key] = False
            return False

        result = False
        try:
            resp = self.session.post(
                "https://libretranslate.com/detect",
                json={"q": combined},
                timeout=TIMEOUT_SECS,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    top = data[0]
                    lang = str(top.get("language", "")).lower()
                    confidence = float(top.get("confidence", 0) or 0)
                    result = bool(lang and lang != "en" and confidence >= 50)
        except (requests.RequestException, ValueError, TypeError):
            pass

        self.lang_cache[cache_key] = result
        return result

    # Backwards-compatible wrapper for older callers.
    def is_foreign_language_title(self, s: str, is_artist_field: bool) -> bool:
        return self.is_foreign_language("" if not is_artist_field else s, s if not is_artist_field else "")

    def lookup_genre_online(self, artist: str, title: str) -> str:
        cache_key = f"{(artist or '').strip().lower()}|{(title or '').strip().lower()}"
        if cache_key in self.genre_cache:
            return self.genre_cache[cache_key]

        result = ""
        for provider in self.providers:
            try:
                result = provider.lookup(self.session, artist, title)
            except Exception:
                result = ""
            if result:
                break

        self.genre_cache[cache_key] = result
        return result

    # Retained for any external/legacy callers that reached past the
    # provider chain directly; now thin wrappers over the default
    # providers rather than separate implementations.
    def _lookup_itunes(self, artist: str, title: str) -> str:
        return ITunesProvider().lookup(self.session, artist, title)

    def _lookup_lastfm(self, artist: str, title: str) -> str:
        return LastFmProvider(lastfm_key=self.lastfm_key).lookup(self.session, artist, title)
