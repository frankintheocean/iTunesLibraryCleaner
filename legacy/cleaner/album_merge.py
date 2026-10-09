"""
Album-merge feature: detects albums that iTunes has split into two (or
more) entries - typically one "main" group with most of the tracks and
a second, smaller group of 1-2 stray tracks that are missing (or have a
slightly different) AlbumArtist/Album/Year, so iTunes treats them as a
separate album instead of folding them back into the real one.

Split-detection (find_split_groups) is pure/offline: it only looks at
track metadata already read from iTunes and returns plain data, so it
can be unit-tested without a live iTunes/COM connection. Applying a
merge (AlbumMergeEngine) is the only part that talks to iTunes, and
reuses itunes_com.do_fields_write_with_fallback - the same
reused-session-first, reconnect-on-failure pattern CleanupEngine
already uses for genre writes - so a flaky COM session is handled the
same way here as everywhere else in the app.
"""
import logging
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field

import requests

import itunes_com
import icons

log = logging.getLogger(__name__)


# ---- offline analysis (no COM) ----

# Precompiled once at import time rather than left as string patterns
# passed to re.sub() on every call - _normalize_key runs twice per
# track (album + album artist), so on a 30k+ track library that's
# 60k+ calls; re.sub still has to look each pattern up in its internal
# cache and re-validate it isn't a compiled Pattern, which precompiling
# avoids. Same matching behavior, just cheaper per call.
_RE_EDITION_SUFFIX = re.compile(r"\b(deluxe|remaster(ed)?|expanded|edition|version|bonus track version)\b")
_RE_BRACKETS = re.compile(r"[\(\)\[\]\{\}]")
_RE_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_RE_LEADING_THE = re.compile(r"^\s*the\s+")
_RE_WHITESPACE = re.compile(r"\s+")


def _normalize_key(s: str) -> str:
    """Loose match key for album-name comparison: casefolded, accents
    stripped, punctuation/whitespace collapsed. Two album names that
    differ only by "The", capitalization, a stray "(Deluxe)" suffix,
    or a curly vs straight apostrophe should still be recognized as
    the same album."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = _RE_EDITION_SUFFIX.sub(" ", s)
    s = _RE_BRACKETS.sub(" ", s)
    s = _RE_NON_ALNUM.sub(" ", s)
    s = _RE_LEADING_THE.sub("", s.strip())
    return _RE_WHITESPACE.sub(" ", s).strip()


@dataclass
class TrackInfo:
    """Minimal, COM-free snapshot of one track's album-identity fields,
    built from itunes_com.safe_get() calls while a live track object is
    still in hand. Everything downstream (grouping, the GUI list,
    merge-plan building) works from this snapshot instead of holding
    onto COM references longer than necessary."""
    persistent_id: str
    artist: str
    album_artist: str
    album: str
    name: str
    track_number: int
    track_count: int
    disc_number: int
    disc_count: int
    year: int
    genre: str
    compilation: bool


@dataclass
class SplitGroup:
    """One detected split: a 'main' cluster of tracks sharing an album
    key/artist plus one or more 'stray' tracks that look like they
    belong to the same album but currently carry different (or blank)
    Album/AlbumArtist metadata."""
    album_key: str
    main_album: str
    main_album_artist: str
    main_tracks: list = field(default_factory=list)
    stray_tracks: list = field(default_factory=list)

    @property
    def total_track_count(self):
        return len(self.main_tracks) + len(self.stray_tracks)


def find_split_groups(tracks, min_main_tracks=3, max_stray_tracks=4):
    """Groups a flat list of TrackInfo by (normalized album, normalized
    album artist) and flags groups that look like a stray remainder of
    a larger album elsewhere in the library - e.g. an 11/12-track main
    group plus a lone track sharing the same album name but a blank or
    slightly different AlbumArtist, or the same album name with a
    trailing "(Bonus Track Version)" that iTunes treated as distinct.

    Only offline grouping/comparison - no iTunes calls. Returns a list
    of SplitGroup, largest main group first. min_main_tracks and
    max_stray_tracks are conservative defaults so a handful of
    genuinely different but similarly-named albums (e.g. two different
    "Greatest Hits") don't get merged by accident - callers/GUI still
    let the user review and deselect any group before applying.
    """
    # First pass: raw (normalized_album, normalized_artist) buckets.
    # AlbumArtist is bucketed on its own (raw, including blank) rather
    # than falling back to Artist here - a blank/mismatched AlbumArtist
    # is exactly the signal that separates a stray track from the main
    # group, so folding it into the same bucket as the main group would
    # hide the split instead of detecting it. The Artist-based fallback
    # is still used later, only to *label* a group's target artist.
    buckets = {}
    for t in tracks:
        album_key = _normalize_key(t.album)
        if not album_key:
            continue  # nothing to group a blank album name against
        artist_key = _normalize_key(t.album_artist)
        buckets.setdefault((album_key, artist_key), []).append(t)

    # Second pass: for each normalized album name, treat the largest
    # same-artist bucket as "main" and fold in any other
    # same-album-name bucket (different/blank artist, or a slightly
    # different album-name variant already merged into the same
    # album_key) as a stray group, as long as it's small enough to be
    # plausibly a stray remainder rather than a genuinely different
    # album that happens to share a title.
    by_album_key = {}
    for (album_key, artist_key), group_tracks in buckets.items():
        by_album_key.setdefault(album_key, []).append((artist_key, group_tracks))

    groups = []
    for album_key, artist_groups in by_album_key.items():
        if len(artist_groups) < 2:
            continue  # only one bucket for this album name - nothing split
        artist_groups.sort(key=lambda ag: len(ag[1]), reverse=True)
        main_artist_key, main_tracks = artist_groups[0]
        if len(main_tracks) < min_main_tracks:
            continue  # main cluster too small to be confident this is "the" album

        stray_tracks = []
        for artist_key, cand_tracks in artist_groups[1:]:
            if len(cand_tracks) > max_stray_tracks:
                continue  # too big to be a stray remainder - likely a real second album
            if not _plausible_stray_artist(cand_tracks, main_tracks):
                continue  # different, non-blank artist - a same-titled but genuinely
                          # different album (e.g. two different artists both with an
                          # album called "The Big Day"), not a split remainder
            stray_tracks.extend(cand_tracks)
        if not stray_tracks:
            continue

        main_album = _most_common([t.album for t in main_tracks])
        main_album_artist = _most_common([t.album_artist for t in main_tracks if t.album_artist.strip()]) \
            or _most_common([t.artist for t in main_tracks])
        groups.append(SplitGroup(
            album_key=album_key,
            main_album=main_album,
            main_album_artist=main_album_artist,
            main_tracks=main_tracks,
            stray_tracks=stray_tracks,
        ))

    groups.sort(key=lambda g: len(g.main_tracks), reverse=True)
    return groups


def _plausible_stray_artist(cand_tracks, main_tracks) -> bool:
    """True if cand_tracks look like they could actually belong to the
    same album as main_tracks, based on the track-level Artist field
    (not just AlbumArtist, which is exactly the field a real stray
    track is missing/wrong on). A candidate bucket only gets folded in
    as a "stray remainder" when its artist is blank (the common real
    case - a track ripped with no AlbumArtist at all), matches the
    main group's artist/album-artist, or one name contains the other
    (handles a lone "feat."/collaborator credit on an otherwise-shared
    album). A candidate with a clearly different, unrelated artist -
    e.g. a same-titled album by a completely different act - is
    rejected here even though it's small enough to look like a stray
    by track count alone; that's a coincidental title match, not a
    split album."""
    main_artist_keys = {_normalize_key(t.artist) for t in main_tracks if t.artist.strip()}
    main_artist_keys |= {_normalize_key(t.album_artist) for t in main_tracks if t.album_artist.strip()}
    main_artist_keys.discard("")
    if not main_artist_keys:
        return True  # nothing to compare against - don't block on missing data

    for t in cand_tracks:
        cand_key = _normalize_key(t.artist)
        if not cand_key:
            continue  # blank track artist - the classic stray-track case
        if any(cand_key == mk or cand_key in mk or mk in cand_key for mk in main_artist_keys):
            continue  # matches, or one contains the other (e.g. a "feat." credit)
        return False  # a genuinely different, unrelated artist on this "stray" track
    return True


# ---- optional online confirmation (iTunes Search API) ----

ITUNES_LOOKUP_TIMEOUT_SECS = 1.5
ITUNES_LOOKUP_RETRY_ATTEMPTS = 2
ITUNES_LOOKUP_RETRY_BACKOFF_BASE = 0.3
ITUNES_LOOKUP_RETRY_STATUS = {500, 502, 503, 504, 429}


class AlbumSearchProvider:
    """Looks up an album's canonical Apple Music `collectionId` and
    `artistId` via the public iTunes Search API (entity=album) - the
    same endpoint online_lookup.ITunesProvider already uses for genre
    lookups, just a different entity. Used only as an optional, opt-in
    confirmation step on top of find_split_groups' offline heuristic
    (see confirm_split_groups_online) - never required for detection
    to work, since it needs network access and a same-titled-album
    catalog match to say anything useful.

    A tiny in-instance cache keeps repeat lookups for the same
    (artist, album) - main group and stray group can share a lookup -
    from hitting the network twice in one scan."""

    def __init__(self, session: "requests.Session | None" = None):
        self.session = session or requests.Session()
        self._cache = {}

    def lookup_collection(self, artist: str, album: str):
        """Returns (collection_id, artist_id) for the best-matching
        album, or (None, None) if no confident match was found (no
        network, no results, or an ambiguous/empty query). Never
        raises - any failure is treated the same as "couldn't
        confirm", which callers must treat as "don't block the
        offline result on this", not as "reject the group"."""
        artist = (artist or "").strip()
        album = (album or "").strip()
        if not artist or not album:
            return None, None

        cache_key = f"{artist.lower()}|{album.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = (None, None)
        for attempt in range(ITUNES_LOOKUP_RETRY_ATTEMPTS):
            try:
                resp = self.session.get(
                    "https://itunes.apple.com/search",
                    params={"media": "music", "entity": "album", "limit": 1,
                            "term": f"{artist} {album}"},
                    timeout=ITUNES_LOOKUP_TIMEOUT_SECS,
                )
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    if results:
                        collection_id = results[0].get("collectionId")
                        artist_id = results[0].get("artistId")
                        if collection_id is not None:
                            result = (collection_id, artist_id)
                    break  # 200 (with or without results) is a real answer - don't retry
                if resp.status_code not in ITUNES_LOOKUP_RETRY_STATUS:
                    break  # non-transient error - retrying won't help
            except (requests.RequestException, ValueError, TypeError):
                pass
            if attempt < ITUNES_LOOKUP_RETRY_ATTEMPTS - 1:
                time.sleep(ITUNES_LOOKUP_RETRY_BACKOFF_BASE)

        self._cache[cache_key] = result
        return result


def confirm_split_groups_online(groups, provider=None, on_status=None):
    """Optional confirmation pass: for each candidate SplitGroup, looks
    up the main group's (artist, album) and the stray group's
    (artist, album) via AlbumSearchProvider and drops the group if
    both sides confidently resolve to *different* Apple Music albums
    (different collectionId, and not even the same artistId) - the
    strongest available signal that this is a coincidental title
    match rather than a real split, catching cases the offline
    heuristic alone can miss.

    This never adds groups the offline pass didn't already find, and
    never removes a group on an inconclusive lookup (no network, no
    match, timeout) - only an explicit "these are two different
    albums by two different artists" result filters a group out.
    Since it depends on network access and catalog coverage, callers
    should treat it strictly as a confidence filter on top of
    find_split_groups' result, not a replacement for it: pass
    find_split_groups(tracks) in, get the same list (each group
    unmodified) minus any group this pass could positively rule out.

    on_status(msg), if given, is called once per group checked, so a
    caller driving a status label has something to show during the
    (network-bound, one-request-per-group) pass - offline detection
    alone is near-instant, so without this a scan would otherwise
    jump straight from "found N possible split album(s)" to nothing
    happening for a few seconds per group."""
    on_status = on_status or (lambda msg: None)
    provider = provider or AlbumSearchProvider()
    confirmed = []
    for group in groups:
        on_status(f"{icons.LOOKUP} Confirming \"{group.main_album}\" online…")
        main_collection, main_artist_id = provider.lookup_collection(
            group.main_album_artist, group.main_album)
        stray_album = _most_common([t.album for t in group.stray_tracks])
        stray_artist = _most_common(
            [t.artist for t in group.stray_tracks if t.artist.strip()]) or group.main_album_artist
        stray_collection, stray_artist_id = provider.lookup_collection(stray_artist, stray_album)

        if (main_collection is not None and stray_collection is not None
                and main_collection != stray_collection
                and main_artist_id is not None and stray_artist_id is not None
                and main_artist_id != stray_artist_id):
            log.debug("Online confirmation rejected split group %r: main=%s/%s stray=%s/%s",
                       group.main_album, main_collection, main_artist_id,
                       stray_collection, stray_artist_id)
            continue  # confidently two different albums by two different artists

        confirmed.append(group)
    return confirmed


def _most_common(values):
    values = [v for v in values if v and v.strip()]
    if not values:
        return ""
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def build_merge_plan(group: SplitGroup):
    """Turns a SplitGroup into a concrete per-track field-write plan:
    only the stray tracks need writes (main tracks are already
    correct), and only fields that actually differ from the target are
    included - do_fields_write_diag() also no-ops unchanged fields, so
    this is a belt-and-suspenders trim that keeps the plan/preview
    honest about what will change.

    Track/disc numbers are intentionally left alone unless a stray
    track has no track number at all (0) - split-off tracks usually
    already carry their correct position within the album; guessing a
    new one from list order would risk being wrong. TrackCount/
    DiscCount are aligned to the main group's values since those two
    fields describe the album as a whole, not the individual track.

    Returns a list of (TrackInfo, fields_dict) pairs, stray tracks
    only, skipping any track that would need no changes at all.
    """
    target_track_count = _most_common_int([t.track_count for t in group.main_tracks]) \
        or group.total_track_count
    target_disc_count = _most_common_int([t.disc_count for t in group.main_tracks]) or 1
    target_year = _most_common_int([t.year for t in group.main_tracks])
    target_genre = _most_common([t.genre for t in group.main_tracks])

    plan = []
    for t in group.stray_tracks:
        fields = {}
        if t.album != group.main_album:
            fields["Album"] = group.main_album
        if t.album_artist != group.main_album_artist:
            fields["AlbumArtist"] = group.main_album_artist
        if target_track_count and t.track_count != target_track_count:
            fields["TrackCount"] = target_track_count
        if target_disc_count and t.disc_count != target_disc_count:
            fields["DiscCount"] = target_disc_count
        if t.disc_number == 0 and target_disc_count:
            fields["DiscNumber"] = 1
        if t.track_number == 0:
            # No position at all - append after the main group's
            # highest known track number rather than leaving it at 0.
            next_num = max([m.track_number for m in group.main_tracks], default=0) + 1
            fields["TrackNumber"] = next_num
        if target_year and t.year == 0:
            fields["Year"] = target_year
        if not t.genre.strip() and target_genre:
            fields["Genre"] = target_genre
        if fields:
            plan.append((t, fields))
    return plan


def _most_common_int(values):
    values = [v for v in values if v]
    if not values:
        return 0
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


# ---- COM-facing: reading the library and applying a merge ----

def read_library_tracks(app, on_status=None, status_every=None):
    """Enumerates the whole library via COM and returns a list of
    TrackInfo snapshots. Runs on the caller's thread - callers should
    invoke this from a background thread the same way CleanupEngine
    does, not directly on the Tk main thread.

    Calls on_status() every status_every tracks so a caller driving a
    progress/status label doesn't sit with a single static "reading
    your library" message for the whole scan - on a library of several
    thousand tracks, enumerate_tracks + two COM calls per track for the
    persistent ID can take a while, and with no interim feedback that
    looks identical to a hang.

    status_every defaults to 100, but scales up automatically on large
    libraries (via _status_interval_for) so a 30k+ track scan doesn't
    spend extra time marshalling status updates onto the Tk thread far
    more often than the label can actually be read."""
    on_status = on_status or (lambda msg: None)
    library = app.LibraryPlaylist
    try:
        total = library.Tracks.Count
    except Exception:
        total = 0
    if status_every is None:
        status_every = _status_interval_for(total)
    out = []
    count = 0
    for track in itunes_com.enumerate_tracks(library):
        count += 1
        if count % status_every == 0:
            on_status(f"{icons.BOOKS} Reading your library… {count} tracks scanned so far")
        pid = itunes_com.get_persistent_id_str(app, track)
        if not pid:
            continue
        out.append(TrackInfo(
            persistent_id=pid,
            artist=str(itunes_com.safe_get(track, "Artist", "")),
            album_artist=str(itunes_com.safe_get(track, "AlbumArtist", "")),
            album=str(itunes_com.safe_get(track, "Album", "")),
            name=str(itunes_com.safe_get(track, "Name", "")),
            track_number=_as_int(itunes_com.safe_get(track, "TrackNumber", 0)),
            track_count=_as_int(itunes_com.safe_get(track, "TrackCount", 0)),
            disc_number=_as_int(itunes_com.safe_get(track, "DiscNumber", 0)),
            disc_count=_as_int(itunes_com.safe_get(track, "DiscCount", 0)),
            year=_as_int(itunes_com.safe_get(track, "Year", 0)),
            genre=str(itunes_com.safe_get(track, "Genre", "")),
            compilation=bool(itunes_com.safe_get(track, "Compilation", False)),
        ))
    on_status(f"{icons.BOOKS} Read {count} tracks. Looking for split albums…")
    return out


def _status_interval_for(total_tracks: int) -> int:
    """Picks a status-update interval that scales with library size:
    small libraries still get feedback every 100 tracks, but a 30k+
    library isn't marshalling a Tk status-label update 300+ times for
    no benefit the user can actually perceive - the label can't be
    read faster than it changes, so widening the interval on large
    libraries only cuts overhead, it never changes what's returned."""
    if total_tracks >= 20000:
        return 500
    if total_tracks >= 5000:
        return 250
    return 100


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class AlbumMergeStats:
    def __init__(self):
        self.total_tracks = 0
        self.current_index = 0
        self.updated_count = 0
        self.failed_count = 0
        self.failed_records = []  # [{"artist","name","persistent_id","reason"}]
        self.stopped = False


class AlbumMergeEngine:
    """Applies a set of already-reviewed merge plans (as built by
    build_merge_plan) to the live library. Mirrors CleanupEngine's
    background-thread + on_progress/on_finished/on_status callback
    shape so gui.py can drive it with the same run_in_background-style
    pattern already used for the main cleanup run and undo.
    """
    def __init__(self, plans, on_progress=None, on_finished=None, on_status=None):
        # plans: list of (TrackInfo, fields_dict) pairs across all
        # groups the user approved, already flattened by the caller.
        self.plans = plans
        self.on_progress = on_progress or (lambda stats: None)
        self.on_finished = on_finished or (lambda stats: None)
        self.on_status = on_status or (lambda msg: None)
        self.stats = AlbumMergeStats()
        self._stop_requested = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_requested.set()

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def _run(self):
        with itunes_com.com_apartment():
            self._run_inner()

    def _run_inner(self):
        self.stats.total_tracks = len(self.plans)
        try:
            app = itunes_com.connect()
        except Exception as e:
            log.debug("Album-merge connect failed: %s", itunes_com.describe_exception(e))
            self.on_status(f"{icons.ERROR} Could not connect to iTunes: {e}")
            self.on_finished(self.stats)
            return

        for i, (track_info, fields) in enumerate(self.plans):
            if self._stop_requested.is_set():
                self.stats.stopped = True
                break
            self.stats.current_index = i + 1
            label = f"{track_info.artist} - {track_info.name}".strip(" -") or "(unknown track)"
            self.on_status(f"{icons.MUSIC} Merging: {label}")

            ok, err = itunes_com.do_fields_write_with_fallback(
                itunes_com.connect, track_info.persistent_id, fields, app=app)
            if ok:
                self.stats.updated_count += 1
            else:
                self.stats.failed_count += 1
                self.stats.failed_records.append({
                    "artist": track_info.artist, "name": track_info.name,
                    "persistent_id": track_info.persistent_id, "reason": err,
                })
                app = None  # force a fresh connect on the next track after a failure
                if app is None:
                    try:
                        app = itunes_com.connect()
                    except Exception:
                        pass
            self.on_progress(self.stats)
            time.sleep(0.05)

        self.on_finished(self.stats)
