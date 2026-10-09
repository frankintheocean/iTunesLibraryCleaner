"""
Core cleanup engine ported from GenreCleanup.hta's processBatch/init/
finishCleanup logic. Runs in a worker thread; reports progress via a
callback so the GUI stays decoupled from iTunes COM calls.
"""
import csv
import datetime
import logging
import os
import sqlite3
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from genre_rules import (
    is_junk_track_name,
    strip_kids_genre,
    genre_lookup_key,
)
from online_lookup import OnlineLookup
import itunes_com
import icons

log = logging.getLogger(__name__)

DEBUG_LOG_NAME = "GenreCleanup_Debug.log"
_file_logging_configured = False


def configure_file_logging(output_folder, level=logging.INFO):
    """Attaches a rotating file handler to the package logger so a
    debug-level history of a run (including exception tracebacks
    already captured via log.exception() calls throughout this
    module) survives after the app closes, separate from the
    user-facing changelog.txt summary. Safe to call more than once -
    only the first call actually attaches a handler. Never raises:
    logging setup failing shouldn't prevent the app from starting."""
    global _file_logging_configured
    if _file_logging_configured:
        return
    try:
        from logging.handlers import RotatingFileHandler
        path = os.path.join(output_folder, DEBUG_LOG_NAME)
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))
        pkg_logger = logging.getLogger(__name__.split(".")[0])
        pkg_logger.addHandler(handler)
        pkg_logger.setLevel(level)
        _file_logging_configured = True
    except Exception:
        # Logging setup is a best-effort convenience; a failure here
        # (e.g. read-only install folder) must never block the app.
        pass


UNDO_LOG_NAME = "GenreCleanup_UndoLog.csv"
PROCESSED_LOG_NAME = "GenreCleanup_Processed.db"
PROCESSED_LOG_NAME_LEGACY = "GenreCleanup_Processed.csv"
CHANGELOG_NAME = "changelog.txt"


DELETE_BATCH_SIZE = 20  # re-enumerate the library once per this many
                        # deletes, instead of after every single delete


class ProcessedCache:
    """Already-processed-track cache, backed by a small SQLite database
    instead of a plain-text file of "pid|genre" lines.

    The old format had two practical problems on real libraries: a
    torn write (crash/power loss mid-write, or two runs started at
    once) could leave the file half-written and silently truncate the
    cache, and a multi-thousand-track library meant re-reading and
    re-writing the *entire* file as one blob on every run. SQLite
    gives atomic commits (a torn write rolls back instead of
    corrupting the file) and can be queried/updated a row at a time,
    which scales to large libraries without holding everything as one
    in-memory set-and-rewrite. The logical key (the same "pid|genre"
    string used before) and one-key-means-one-processed-track
    semantics are unchanged - this is a storage swap, not a behavior
    change.

    All public methods are safe to call from a single writer thread;
    an internal lock still guards the in-memory mirror so a future
    caller reading from another thread mid-run can't observe a
    half-updated set (see CleanupEngine's processed-cache methods)."""

    def __init__(self, db_path, legacy_csv_path=None, on_error=None):
        self.db_path = db_path
        self.legacy_csv_path = legacy_csv_path
        self.on_error = on_error or (lambda msg: None)
        self._lock = threading.Lock()
        self._keys = set()
        self._dirty_keys = []  # pending inserts not yet committed
        self._conn = None

    def load(self):
        """Opens (creating if needed) the SQLite cache, migrating rows
        out of the legacy plain-text file on first use if the .db
        doesn't exist yet but the old .csv does. Read/parse failures
        are logged and treated as an empty cache (matching the old
        behavior of falling back to "nothing cached") rather than
        crashing the run."""
        keys = set()
        try:
            is_new_db = not os.path.exists(self.db_path)
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS processed (cache_key TEXT PRIMARY KEY)"
            )
            self._conn.commit()
            if is_new_db and self.legacy_csv_path and os.path.exists(self.legacy_csv_path):
                keys = self._migrate_legacy_csv()
            else:
                for (row,) in self._conn.execute("SELECT cache_key FROM processed"):
                    keys.add(row)
        except (OSError, sqlite3.Error) as e:
            log.exception("Failed to open processed-track cache at %s", self.db_path)
            self.on_error(f"{icons.WARNING} Could not open the processed-track cache ({e}). Every track will be re-checked this run.")
            self._conn = None
        with self._lock:
            self._keys = keys
            self._dirty_keys = []

    def _migrate_legacy_csv(self):
        keys = set()
        try:
            with open(self.legacy_csv_path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        keys.add(line)
            if keys and self._conn is not None:
                self._conn.executemany(
                    "INSERT OR IGNORE INTO processed (cache_key) VALUES (?)",
                    [(k,) for k in keys],
                )
                self._conn.commit()
        except OSError:
            log.exception("Failed to migrate legacy processed-track cache from %s", self.legacy_csv_path)
        return keys

    def contains(self, cache_key):
        with self._lock:
            return cache_key in self._keys

    def mark(self, cache_key):
        """Records cache_key as processed, in memory immediately and
        in the database on the next flush(). Returns True if this was
        a new key (matching the old set-add-and-mark-dirty behavior),
        False if it was already present."""
        with self._lock:
            if cache_key in self._keys:
                return False
            self._keys.add(cache_key)
            self._dirty_keys.append(cache_key)
            return True

    def flush(self):
        """Commits any keys marked since the last flush. Safe to call
        even if nothing is dirty or the database failed to open."""
        with self._lock:
            pending = self._dirty_keys
            self._dirty_keys = []
        if not pending or self._conn is None:
            return
        try:
            self._conn.executemany(
                "INSERT OR IGNORE INTO processed (cache_key) VALUES (?)",
                [(k,) for k in pending],
            )
            self._conn.commit()
        except sqlite3.Error as e:
            log.exception("Failed to write processed-track cache to %s", self.db_path)
            self.on_error(f"{icons.WARNING} Could not save the processed-track cache ({e}).")
            # Put the keys back so a later flush() can retry rather
            # than losing them outright.
            with self._lock:
                self._dirty_keys = pending + self._dirty_keys

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None

    def snapshot(self):
        with self._lock:
            return list(self._keys)


def vacuum_processed_cache(output_folder: str):
    """Maintenance action for Settings: VACUUMs the processed-track
    cache database to reclaim space and returns (ok, message).

    VACUUM alone doesn't remove rows for tracks later deleted from
    iTunes (this module has no cheap way to tell "orphaned" rows
    apart without a live COM connection to check every persistent ID
    against the current library) - it only rewrites the file to
    reclaim space already freed by SQLite's internal free-page
    tracking, which is still worth doing periodically since the file
    otherwise never shrinks even as old rows are superseded.
    """
    db_path = os.path.join(output_folder, PROCESSED_LOG_NAME)
    if not os.path.exists(db_path):
        return True, "No processed-track cache found - nothing to clean."
    try:
        before = os.path.getsize(db_path)
        conn = sqlite3.connect(db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM processed").fetchone()[0]
            conn.execute("VACUUM")
        finally:
            conn.close()
        after = os.path.getsize(db_path)
        saved = max(0, before - after)
        return True, f"{icons.SUCCESS} Cache cleaned: {count} entries, {saved // 1024} KB reclaimed."
    except (OSError, sqlite3.Error) as e:
        log.exception("Failed to vacuum processed-track cache at %s", db_path)
        return False, f"{icons.WARNING} Could not clean the cache: {e}"


def clear_processed_cache(output_folder: str):
    """Maintenance action for Settings: deletes all rows from the
    processed-track cache (forces every track to be re-checked on the
    next run) and VACUUMs afterward. Use this to drop stale/orphaned
    entries for tracks later removed from iTunes, since they can't be
    identified individually without a live library scan.
    Returns (ok, message)."""
    db_path = os.path.join(output_folder, PROCESSED_LOG_NAME)
    if not os.path.exists(db_path):
        return True, "No processed-track cache found - nothing to clean."
    try:
        conn = sqlite3.connect(db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM processed").fetchone()[0]
            conn.execute("DELETE FROM processed")
            conn.commit()
            conn.execute("VACUUM")
        finally:
            conn.close()
        return True, f"{icons.SUCCESS} Cache cleared: {count} entries removed. Every track will be re-checked on the next run."
    except (OSError, sqlite3.Error) as e:
        log.exception("Failed to clear processed-track cache at %s", db_path)
        return False, f"{icons.WARNING} Could not clear the cache: {e}"


class _ScopeResolutionError(Exception):
    """Internal: a named scope playlist couldn't be resolved via COM.
    Caught in _prepare_run() and turned into an on_status() message."""
    pass


class CleanupOptions:
    def __init__(self, unknown_lookup=True, foreign_detect=True,
                 dry_run=False, force_rescan=False,
                 lastfm_user="", lastfm_key="", prefer_lastfm=False,
                 output_folder=None, scope_playlist=None,
                 scope_playlists=None, scope_mode="include",
                 delete_batch_size=None):
        self.unknown_lookup = unknown_lookup
        self.foreign_detect = foreign_detect
        self.dry_run = dry_run
        self.force_rescan = force_rescan
        self.lastfm_user = lastfm_user
        self.lastfm_key = lastfm_key
        self.prefer_lastfm = prefer_lastfm
        self.output_folder = output_folder or os.getcwd()
        # delete_batch_size: how many junk-track deletes to accumulate
        # before re-enumerating the library to recover from COM index
        # drift (see DELETE_BATCH_SIZE). None/0/negative falls back to
        # the module default.
        self.delete_batch_size = delete_batch_size if delete_batch_size and delete_batch_size > 0 else DELETE_BATCH_SIZE
        # scope_playlists: list of playlist names the run is scoped to,
        # or None/[] for "whole library". scope_mode is "include" (only
        # process tracks in these playlists) or "exclude" (process the
        # whole library except tracks in these playlists).
        # scope_playlist (singular) is kept as a back-compat alias: a
        # single-name caller still works and is normalized into the list
        # form below, so existing integrations/tests aren't broken.
        names = list(scope_playlists) if scope_playlists else []
        if scope_playlist and scope_playlist not in names:
            names.append(scope_playlist)
        self.scope_playlists = names
        self.scope_mode = scope_mode if scope_mode in ("include", "exclude") else "include"

    @property
    def scope_playlist(self):
        """Back-compat: the first scoped playlist name, or None. Prefer
        scope_playlists/scope_mode for new code - this only makes sense
        for single-playlist include-mode scopes."""
        return self.scope_playlists[0] if self.scope_playlists else None


class CleanupStats:
    def __init__(self):
        self.total_tracks = 0
        self.current_index = 0
        self.changed_count = 0
        self.deleted_count = 0
        self.failed_write_count = 0
        self.failed_delete_count = 0
        self.skipped_fixed_count = 0
        self.delete_diag_lines = []
        # Structured per-track failure records (drill-down for the GUI's
        # run-review popup), one dict per failed write/delete:
        # {"kind": "write"|"delete", "artist": str, "name": str,
        #  "persistent_id": str, "reason": str}. delete_diag_lines above
        # is kept as-is (changelog.txt still reads it as plain text).
        self.failed_records = []
        self.start_time = None
        self.stopped = False
        self.paused = False
        # Which sub-phase the current track is being handled by, purely
        # for the GUI's per-phase progress breakdown - "deleting" while
        # a junk-named track is being removed, "genres" while a track is
        # having its genre checked/rewritten. Does not affect control
        # flow; both phases interleave per-track in the same pass (see
        # _process_one_index), this just labels which one is active.
        self.phase = "genres"
        # Running per-phase counts of tracks handled so far, so the GUI
        # can render a two-segment breakdown (deleted-junk vs
        # genre-processed) instead of one blended percentage. Both
        # counters only ever grow monotonically within a run.
        self.deleting_phase_count = 0
        self.genres_phase_count = 0


class CleanupEngine:
    """Runs the cleanup pass in a background thread. GUI code should
    create one instance per run and poll/observe `stats` plus the
    `on_progress`/`on_finished` callbacks."""

    def __init__(self, options: CleanupOptions,
                 on_progress=None, on_finished=None, on_status=None):
        self.options = options
        self.on_progress = on_progress or (lambda stats: None)
        self.on_finished = on_finished or (lambda stats: None)
        self.on_status = on_status or (lambda msg: None)

        self.stats = CleanupStats()
        self._stop_requested = threading.Event()
        # Pause uses a "resume" event that the loop waits on when
        # paused, rather than a plain flag - Event.wait() blocks the
        # worker thread cheaply (no polling loop / busy-wait) until
        # resume() sets it again. It starts "set" (i.e. not paused).
        self._resume_event = threading.Event()
        self._resume_event.set()
        self._thread = None
        self._reenumerate_warned = False

        self.lookup = OnlineLookup(
            lastfm_user=options.lastfm_user,
            lastfm_key=options.lastfm_key,
            prefer_lastfm=options.prefer_lastfm,
        )

        # Online language detection and missing-genre lookup are independent.
        # Overlap them for blank-genre tracks so network latency no longer
        # stacks up serially on every song. iTunes COM writes remain on the
        # dedicated worker thread.
        self._lookup_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="LibraryCleanerLookup")

        self.undo_log_rows = []  # list of dicts: action, persistent_id, old_genre, new_genre, artist, name
        self.undo_log_path = os.path.join(options.output_folder, UNDO_LOG_NAME)
        self.processed_log_path = os.path.join(options.output_folder, PROCESSED_LOG_NAME)
        self._processed_log_path_legacy = os.path.join(options.output_folder, PROCESSED_LOG_NAME_LEGACY)
        self.changelog_path = os.path.join(options.output_folder, CHANGELOG_NAME)
        # SQLite-backed replacement for the old plain-text
        # "pid|genre"-per-line cache file; see ProcessedCache's
        # docstring. Thread-safe internally (see its own lock), so
        # any future GUI-thread reader is already safe against the
        # worker thread's mutations.
        self.processed_cache = ProcessedCache(self.processed_log_path, self._processed_log_path_legacy,
                                               on_error=self.on_status)

    def _status(self, msg, level=logging.INFO):
        """Single choke point for user-facing status messages: always
        goes to the Python logger (so a debug log file captures the
        full run history with real levels/timestamps), and also calls
        on_status() with the same text for the GUI's live status label
        and log pane - on_status remains exactly the UI-facing subset
        it always was, just routed through here instead of being the
        only record of what happened."""
        log.log(level, msg)
        self.on_status(msg)

    # ---- public control ----
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_requested.set()
        # Waking a paused loop on stop so it can observe the stop
        # request and exit promptly, instead of sitting blocked on
        # _resume_event.wait() forever.
        self._resume_event.set()

    def pause(self):
        """Pauses the run in place: the worker thread blocks right
        before its next track, keeping its exact position in
        track_refs, its in-memory undo-log rows, and its
        processed-id cache - unlike stop(), nothing is torn down, so
        resume() continues from exactly where it left off rather than
        needing a fresh run from the start."""
        self.stats.paused = True
        self._resume_event.clear()

    def resume(self):
        self.stats.paused = False
        self._resume_event.set()

    def is_paused(self):
        return self.stats.paused

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    # ---- internal ----
    def _load_processed_cache(self):
        self.processed_cache.load()

    def _is_track_already_processed(self, cache_key):
        return self.processed_cache.contains(cache_key)

    def _mark_track_processed(self, record_key):
        self.processed_cache.mark(record_key)

    def _run(self):
        try:
            with itunes_com.com_apartment():
                self._run_inner()
        finally:
            try:
                self._lookup_executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            self.processed_cache.close()

    def _run_inner(self):
        setup = self._prepare_run()
        if setup is None:
            return
        app, scope_playlist, track_refs = setup

        self._pending_delete_count = 0
        self.stats.total_tracks = len(track_refs)
        self.stats.start_time = time.time()

        i = 0
        while i < len(track_refs):
            if self._stop_requested.is_set():
                self.stats.stopped = True
                break
            self._resume_event.wait()
            if self._stop_requested.is_set():
                self.stats.stopped = True
                break

            if self._pending_delete_count >= self.options.delete_batch_size:
                track_refs = self._reenumerate_from(app, scope_playlist, track_refs, i - 1)
                if i >= len(track_refs):
                    self.stats.total_tracks = len(track_refs)
                    break

            track_refs, i = self._process_one_index(app, track_refs, i, scope_playlist)

        self._finish()

    def _prepare_run(self):
        """Connects to iTunes, loads the processed-id cache, resolves
        the scope playlist (if any), and enumerates the tracks to
        process. Returns (app, scope_playlist, track_refs) on success,
        or None if setup failed - in which case on_finished has
        already been called and _run_inner should return immediately."""
        self._status(f"{icons.PLUG} Connecting to iTunes...")
        try:
            app = itunes_com.connect()
            library = app.LibraryPlaylist
        except Exception as e:
            log.debug("iTunes connect failed: %s", itunes_com.describe_exception(e))
            self._status(f"{icons.ERROR} Could not connect to iTunes: {e}", level=logging.ERROR)
            self.on_finished(self.stats)
            return None

        self._load_processed_cache()
        try:
            track_refs, scope_desc = self._resolve_scope(app, library)
        except _ScopeResolutionError as e:
            self._status(str(e), level=logging.WARNING)
            self.on_finished(self.stats)
            return None

        self._status(f"{icons.BOOKS} Reading {scope_desc}...")
        try:
            track_refs = list(track_refs)
        except Exception as e:
            log.debug("Library read failed: %s", itunes_com.describe_exception(e))
            self._status(f"{icons.ERROR} Could not read the library: {e}", level=logging.ERROR)
            self.on_finished(self.stats)
            return None

        # scope_playlist is kept only as the legacy "single COM playlist
        # object" passed around internally (junk-delete reenumeration);
        # with multi-playlist/exclude scopes there's no single object to
        # hand back, so downstream code re-resolves scope from
        # self.options on demand instead (see _reenumerate_from).
        scope_playlist = None
        if self.options.scope_mode == "include" and len(self.options.scope_playlists) == 1:
            scope_playlist = itunes_com.get_playlist_by_name(app, self.options.scope_playlists[0])

        return app, scope_playlist, track_refs

    def _resolve_scope(self, app, library):
        """Returns (track_iterable, description) honoring
        scope_playlists/scope_mode. Raises _ScopeResolutionError with a
        user-facing message if a named playlist can't be found."""
        names = self.options.scope_playlists
        if not names:
            return itunes_com.enumerate_tracks(library), "your library"

        playlists = []
        for pname in names:
            pl = itunes_com.get_playlist_by_name(app, pname)
            if pl is None:
                raise _ScopeResolutionError(f'{icons.ERROR} Playlist "{pname}" not found.')
            playlists.append((pname, pl))

        if self.options.scope_mode == "include":
            if len(playlists) == 1:
                desc = f'playlist "{playlists[0][0]}"'
            else:
                desc = f"{len(playlists)} selected playlists"
            return self._enumerate_multi(pl for _, pl in playlists), desc

        # exclude mode: whole library minus tracks that appear in any of
        # the named playlists (matched by persistent ID, since a track's
        # COM identity differs between the library playlist and a
        # regular playlist's own Tracks collection).
        excluded_ids = set()
        for _, pl in playlists:
            for track in itunes_com.enumerate_tracks(pl):
                pid = itunes_com.get_persistent_id_str(app, track)
                if pid:
                    excluded_ids.add(pid)
        desc = f"your library (excluding {len(playlists)} playlist{'s' if len(playlists) != 1 else ''})"
        return self._enumerate_excluding(app, library, excluded_ids), desc

    @staticmethod
    def _enumerate_multi(playlist_objs):
        """Chains enumerate_tracks() across several playlists, skipping
        a track's later occurrences if it appears in more than one of
        the selected playlists so it isn't processed twice."""
        seen_locations = set()
        for pl in playlist_objs:
            for track in itunes_com.enumerate_tracks(pl):
                loc = itunes_com.safe_get(track, "Location", "")
                key = loc or id(track)
                if key in seen_locations:
                    continue
                seen_locations.add(key)
                yield track

    @staticmethod
    def _enumerate_excluding(app, library, excluded_ids):
        for track in itunes_com.enumerate_tracks(library):
            pid = itunes_com.get_persistent_id_str(app, track)
            if pid and pid in excluded_ids:
                continue
            yield track

    def _process_one_index(self, app, track_refs, i, scope_playlist):
        """Handles a single track at index i (junk-delete check, then
        genre processing), reports progress, and returns the next
        (track_refs, index) to process. track_refs is returned back to
        the caller because a junk delete may trigger an eager mid-batch
        reenumeration that replaces the list (see _handle_junk_delete)."""
        track = track_refs[i]
        self.stats.current_index = i + 1
        self._status(f"{itunes_com.safe_get(track, 'Artist', '')} - {itunes_com.safe_get(track, 'Name', '')}".strip(" -"), level=logging.DEBUG)

        name = itunes_com.safe_get(track, "Name", "")
        location = itunes_com.safe_get(track, "Location", "")
        self.stats.phase = "deleting" if is_junk_track_name(name, location) else "genres"

        deleted, track_refs = self._handle_junk_delete(app, track, i, track_refs, scope_playlist)
        if deleted:
            self.stats.deleting_phase_count += 1
            self.on_progress(self.stats)
            return track_refs, i + 1

        track = track_refs[i]
        self.stats.phase = "genres"
        self._process_track(app, track)
        self.stats.genres_phase_count += 1
        self.on_progress(self.stats)
        return track_refs, i + 1

    def _handle_junk_delete(self, app, track, index, track_refs, scope_playlist):
        """Delete malformed imported track names and maintain batch
        reindexing. Returns (was_junk, track_refs) - track_refs is the
        list the caller should keep using: unchanged unless an eager
        mid-batch reenumeration replaced it (see below)."""
        name = itunes_com.safe_get(track, "Name", "")
        location = itunes_com.safe_get(track, "Location", "")
        if not is_junk_track_name(name, location):
            return False, track_refs

        junk_log_name = name.strip() if name.strip() else _filename_stem(location)
        pid = itunes_com.get_persistent_id_str(app, track)
        if self.options.dry_run:
            self.stats.deleted_count += 1
            return True, track_refs

        ok, err = itunes_com.do_track_delete(itunes_com.connect, pid, app=app)
        if ok:
            self.stats.deleted_count += 1
            self.undo_log_rows.append({"action": "DELETED", "persistent_id": pid,
                                       "old_genre": "", "new_genre": "",
                                       "artist": itunes_com.safe_get(track, "Artist", ""),
                                       "name": junk_log_name})
            self._pending_delete_count += 1
            if self._pending_delete_count >= self.options.delete_batch_size:
                # Eager batch boundary for large junk clusters: the
                # reenumerated list must be handed back to the caller
                # (_run_inner's loop), since _reenumerate_from returns a
                # new list rather than mutating track_refs in place -
                # discarding it here would silently reset
                # _pending_delete_count without ever applying the
                # refreshed list, defeating this batch boundary entirely.
                track_refs = self._reenumerate_from(app, scope_playlist, track_refs, index)
            time.sleep(0.6)
        else:
            self.stats.delete_diag_lines.append(f"Delete | {junk_log_name} | {err}")
            self.stats.failed_delete_count += 1
            self.stats.failed_records.append({
                "kind": "delete", "artist": itunes_com.safe_get(track, "Artist", ""),
                "name": junk_log_name, "persistent_id": pid, "reason": err,
            })
        return True, track_refs

    def _process_track(self, app, track):
        """Process one non-junk track: cache, language, then genre."""
        old_genre = itunes_com.safe_get(track, "Genre", "")
        artist = itunes_com.safe_get(track, "Artist", "")
        name = itunes_com.safe_get(track, "Name", "")
        pid = itunes_com.get_persistent_id_str(app, track)
        cache_key = f"{pid}|{old_genre}"
        if pid and not self.options.force_rescan and self._is_track_already_processed(cache_key):
            self.stats.skipped_fixed_count += 1
            return "skip"

        genre_written, final_genre = self._handle_genre_update(app, track, pid, old_genre, artist, name)
        if pid and not genre_written:
            record_key = f"{pid}|{final_genre}"
            self._mark_track_processed(record_key)
        return "processed"

    def _handle_genre_update(self, app, track, pid, old_genre, artist, name):
        """Apply foreign-language priority, then mapping/online lookup."""
        genre_written = False
        final_genre = old_genre
        already_international = old_genre.strip() == "International"
        blank_genre = not old_genre.strip()

        # Run independent network checks concurrently. Online genre lookup
        # remains restricted to genuinely blank Genre fields.
        genre_future = None
        foreign_future = None
        if blank_genre and self.options.unknown_lookup:
            genre_future = self._lookup_executor.submit(self.lookup.lookup_genre_online, artist, name)
        if self.options.foreign_detect and not already_international:
            foreign_future = self._lookup_executor.submit(self.lookup.is_foreign_language, artist, name)

        is_foreign = False
        if foreign_future is not None:
            try:
                is_foreign = bool(foreign_future.result())
            except Exception:
                is_foreign = False
        if is_foreign:
            if genre_future is not None:
                genre_future.cancel()
            genre_written = self._write_genre(app, track, pid, old_genre, "International", artist, name)
            return genre_written, "International" if genre_written else final_genre

        if blank_genre:
            looked_up = ""
            if genre_future is not None:
                try:
                    looked_up = genre_future.result()
                except Exception:
                    pass
            if looked_up:
                genre_written = self._write_genre(app, track, pid, old_genre, looked_up, artist, name)
                if genre_written:
                    final_genre = looked_up
            return genre_written, final_genre

        clean_genre = strip_kids_genre(old_genre.strip()) if "kids" in old_genre.lower() else old_genre.strip()
        clean_genre = " ".join(clean_genre.split())
        if not clean_genre:
            # A non-empty source genre that becomes empty after the Kids cleanup
            # is intentionally treated as blank, so online lookup may fill it.
            if self.options.unknown_lookup:
                looked_up = self.lookup.lookup_genre_online(artist, name)
                if looked_up:
                    genre_written = self._write_genre(app, track, pid, old_genre, looked_up, artist, name)
                    if genre_written:
                        final_genre = looked_up
            return genre_written, final_genre

        new_genre = genre_lookup_key(clean_genre)
        if new_genre != clean_genre:
            if old_genre != new_genre:
                genre_written = self._write_genre(app, track, pid, old_genre, new_genre, artist, name)
                if genre_written:
                    final_genre = new_genre
        elif old_genre != clean_genre:
            genre_written = self._write_genre(app, track, pid, old_genre, clean_genre, artist, name)
            if genre_written:
                final_genre = clean_genre
        else:
            self.stats.skipped_fixed_count += 1
        return genre_written, final_genre

    def _reenumerate_from(self, app, scope_playlist, track_refs, upto_index):
        """Re-walks the library (or scope playlist) fresh via COM and
        splices the result in after upto_index (inclusive), to recover
        from index drift caused by deletes. Resets the pending-delete
        batch counter. Same fallback-on-failure behavior as before:
        leaves track_refs untouched if the re-enumeration itself fails,
        but now surfaces a one-time warning via on_status when that
        happens, since silently falling back on every batch could mean
        processing against increasingly stale COM references without
        the user ever seeing why."""
        try:
            fresh_app = itunes_com.connect()
            try:
                remaining = list(self._resolve_scope(fresh_app, fresh_app.LibraryPlaylist)[0])
            except _ScopeResolutionError:
                # A scoped playlist vanished mid-run (renamed/deleted in
                # iTunes) - fall back to the whole library rather than
                # aborting the in-progress run over it.
                remaining = list(itunes_com.enumerate_tracks(fresh_app.LibraryPlaylist))
            new_refs = track_refs[: upto_index + 1] + remaining[upto_index + 1:]
            self.stats.total_tracks = len(new_refs)
            self._pending_delete_count = 0
            return new_refs
        except Exception as e:
            if not self._reenumerate_warned:
                self._reenumerate_warned = True
                log.warning("Re-enumeration failed; continuing with the existing track list: %s", e)
                log.debug("Re-enumeration failure detail: %s", itunes_com.describe_exception(e))
                self._status(
                    f"{icons.WARNING} Couldn't refresh the track list after recent deletes "
                    "(iTunes may be busy) - continuing with the existing list, "
                    "which may be briefly stale. This warning won't repeat this run.",
                    level=logging.WARNING,
                )
            return track_refs

    def _write_genre(self, app, track, pid, old_genre, new_genre, artist, name) -> bool:
        if self.options.dry_run:
            self.stats.changed_count += 1
            return True
        ok, err = itunes_com.do_genre_write_with_fallback(
            itunes_com.connect, pid, new_genre, app=app, track=track)
        if ok:
            self.stats.changed_count += 1
            self.undo_log_rows.append({
                "action": "GENRE", "persistent_id": pid,
                "old_genre": old_genre, "new_genre": new_genre,
                "artist": artist, "name": name,
            })
            return True
        self.stats.failed_write_count += 1
        label = f"{artist} - {name}".strip(" -") or "(unknown track)"
        self.stats.delete_diag_lines.append(f"Genre write | {label} | {err}")
        self.stats.failed_records.append({
            "kind": "write", "artist": artist, "name": name,
            "persistent_id": pid, "reason": err,
            "attempted_genre": new_genre,
        })
        return False

    def _finish(self):
        try:
            self._lookup_executor.shutdown(wait=True, cancel_futures=False)
        except Exception:
            pass
        self._flush_undo_log()
        self._flush_processed_log()
        self._write_changelog()
        self.on_finished(self.stats)

    def _flush_undo_log(self):
        if self.options.dry_run or not self.undo_log_rows:
            return
        try:
            # Write to a temp file in the same folder, then atomically
            # replace undo_log.csv (os.replace), matching the pattern
            # already used for settings.json - a crash/power-loss
            # mid-write can no longer leave a truncated/corrupt undo
            # log that "Undo Last Run" would then misread.
            fd, tmp_path = tempfile.mkstemp(prefix=".undo-", suffix=".tmp",
                                             dir=os.path.dirname(self.undo_log_path) or ".")
            try:
                with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(["action", "persistent_id", "old_genre", "new_genre", "artist", "name"])
                    for row in self.undo_log_rows:
                        writer.writerow([
                            row["action"], row["persistent_id"], row["old_genre"],
                            row["new_genre"], row["artist"], row["name"],
                        ])
                os.replace(tmp_path, self.undo_log_path)
            except Exception:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as e:
            # Undo log failing to write is significant - it means "Undo
            # Last Run" won't be available for this run - so this is
            # logged and surfaced to the user instead of silently lost.
            log.exception("Failed to write undo log to %s", self.undo_log_path)
            self._status(f"{icons.WARNING} Could not save the undo log ({e.strerror or e}). Undo won't be available for this run.", level=logging.WARNING)

    def _flush_processed_log(self):
        if self.options.dry_run:
            return
        # ProcessedCache.flush() commits any pending marks in its own
        # try/except and logs+no-ops on failure (retrying the pending
        # keys on the next flush) rather than raising, so a disk
        # problem here can't take down the rest of _finish().
        self.processed_cache.flush()

    def _scope_description(self) -> str:
        names = self.options.scope_playlists
        if not names:
            return "Entire library"
        if self.options.scope_mode == "exclude":
            return f"Entire library, excluding: {', '.join(names)}"
        return names[0] if len(names) == 1 else f"{len(names)} playlists: {', '.join(names)}"

    def _write_changelog(self):
        try:
            # Same temp-file + os.replace atomic-write pattern as the undo
            # log and settings.json, so a crash/power-loss mid-write can't
            # leave a half-written changelog.txt behind.
            fd, tmp_path = tempfile.mkstemp(prefix=".changelog-", suffix=".tmp",
                                             dir=os.path.dirname(self.changelog_path) or ".")
            try:
                with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
                    self._write_changelog_body(f)
                os.replace(tmp_path, self.changelog_path)
            except Exception:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as e:
            # The changelog.txt is a convenience summary, not required
            # for correctness (undo/processed-cache are separate files),
            # but a silent failure here still hides real disk problems
            # from the user, so it's logged and surfaced like the others.
            log.exception("Failed to write changelog to %s", self.changelog_path)
            self._status(f"{icons.WARNING} Could not save changelog.txt ({e.strerror or e}).", level=logging.WARNING)

    def _write_changelog_body(self, f):
        f.write("iTunes Genre Cleanup - Changelog\n")
        f.write(f"Run finished: {datetime.datetime.now()}\n")
        status = "Stopped early by user" if self.stats.stopped else (
            "Dry run (no changes written)" if self.options.dry_run else "Completed")
        f.write(f"Status: {status}\n")
        f.write(f"Mode: {'Dry run' if self.options.dry_run else 'Live'}\n")
        f.write(f"Unknown-genre lookup: {'On' if self.options.unknown_lookup else 'Off'}\n")
        f.write(f"Foreign-title detection: {'On' if self.options.foreign_detect else 'Off'}\n")
        f.write(f"Force full re-scan: {'On' if self.options.force_rescan else 'Off'}\n")
        f.write(f"Scope: {self._scope_description()}\n")
        f.write(f"Tracks processed: {self.stats.current_index} / {self.stats.total_tracks}\n")
        f.write(f"Genres changed: {self.stats.changed_count}\n")
        f.write(f"Tracks deleted (junk): {self.stats.deleted_count}\n")
        f.write(f"Already-fixed tracks skipped: {self.stats.skipped_fixed_count}\n")
        if self.stats.failed_write_count:
            f.write(f"Failed writes: {self.stats.failed_write_count} (iTunes rejected these)\n")
        if self.stats.failed_delete_count:
            f.write(f"Failed deletes: {self.stats.failed_delete_count} (iTunes rejected these - will retry next run)\n")
        if self.stats.delete_diag_lines:
            f.write("\n---- Failure diagnostics ----\n")
            for line in self.stats.delete_diag_lines:
                f.write(line + "\n")
        f.write("\n---- Genre changes ----\n")
        if self.options.dry_run:
            f.write("(Dry run - no undo log was written, so per-track detail isn't available here.\n")
            f.write(" Re-run without Dry Run to get a full per-track list.)\n")
        elif not self.undo_log_rows:
            f.write("(No genre changes or deletions this run.)\n")
        else:
            for row in self.undo_log_rows:
                if row["action"] == "GENRE":
                    f.write(f"{row['artist']} - {row['name']}: \"{row['old_genre']}\" -> \"{row['new_genre']}\"\n")
                elif row["action"] == "DELETED":
                    f.write(f"{row['artist']} - {row['name']}: DELETED (junk filename)\n")


def _filename_stem(location: str) -> str:
    if not location:
        return ""
    file_only = location.replace("/", "\\").rsplit("\\", 1)[-1]
    if "." in file_only:
        file_only = file_only.rsplit(".", 1)[0]
    return file_only.strip()


def retry_failed_records(failed_records, on_status=None):
    """Re-attempts just the writes/deletes that failed on a previous
    run (as recorded in CleanupStats.failed_records), by persistent ID.
    Returns a fresh list of records that are still failing (empty if
    everything succeeded this time), so the caller can update its
    failure list/UI without needing a whole new cleanup run.

    Runs in the caller's own worker thread, same COM-apartment pattern
    as undo_last_run()."""
    on_status = on_status or (lambda msg: None)
    still_failed = []
    with itunes_com.com_apartment():
        try:
            app = itunes_com.connect()
            app.LibraryPlaylist  # connectivity check - result unused, failure is what matters here
        except Exception as e:
            log.error("Could not connect to iTunes for retry: %s", e)
            log.debug("Retry connect failure detail: %s", itunes_com.describe_exception(e))
            on_status(f"{icons.CLOSE} Could not connect to iTunes: {e}")
            return list(failed_records)

        retried = 0
        succeeded = 0
        for rec in failed_records:
            pid = rec.get("persistent_id", "")
            if not pid:
                still_failed.append(rec)
                continue
            retried += 1
            if rec.get("kind") == "delete":
                ok, err = itunes_com.do_track_delete(itunes_com.connect, pid, app=app)
            else:
                ok, err = itunes_com.do_genre_write_with_fallback(
                    itunes_com.connect, pid, rec.get("attempted_genre", ""), app=app)
            if ok:
                succeeded += 1
            else:
                still_failed.append({**rec, "reason": err})

        msg = f"{icons.REPEAT} Retry complete: {succeeded}/{retried} succeeded"
        if still_failed:
            msg += f", {len(still_failed)} still failing"
        log.info(msg)
        on_status(msg)
    return still_failed


def undo_last_run(output_folder: str, on_status=None):
    """Reads GenreCleanup_UndoLog.csv and reverses every GENRE row.
    DELETED rows can't be restored automatically via COM - counted and
    reported instead of silently pretending they were reverted."""
    on_status = on_status or (lambda msg: None)
    undo_log_path = os.path.join(output_folder, UNDO_LOG_NAME)
    if not os.path.exists(undo_log_path):
        log.warning("Undo requested but no undo log found at %s", undo_log_path)
        on_status(f"{icons.ERROR} No undo log found - nothing to undo.")
        return

    # Called from its own worker thread (see gui.py's on_undo), same as
    # CleanupEngine._run - com_apartment() pairs the CoInitialize/
    # CoUninitialize calls structurally (enter/exit) instead of relying
    # on a comment to keep a manual CoUninitialize() in sync with it.
    with itunes_com.com_apartment():
        _undo_last_run_inner(output_folder, on_status, undo_log_path)


def _undo_last_run_inner(output_folder: str, on_status, undo_log_path: str):
    log.info("Undoing last run...")
    on_status(f"{icons.UNDO} Undoing last run...")
    try:
        app = itunes_com.connect()
        library = app.LibraryPlaylist
    except Exception as e:
        log.error("Could not connect to iTunes for undo: %s", e)
        log.debug("Undo connect failure detail: %s", itunes_com.describe_exception(e))
        on_status(f"{icons.CLOSE} Could not connect to iTunes: {e}")
        return

    reverted = 0
    missing = 0
    deleted_skipped = 0

    with open(undo_log_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            action = row.get("action", "")
            pid = row.get("persistent_id", "")
            old_genre = row.get("old_genre", "")
            if action == "GENRE" and pid:
                track = itunes_com.item_by_persistent_id(library.Tracks, pid)
                if track is not None:
                    if itunes_com.do_genre_write(track, old_genre):
                        reverted += 1
                    else:
                        missing += 1
                else:
                    missing += 1
            elif action == "DELETED":
                deleted_skipped += 1

    msg = f"{icons.SUCCESS} Undo complete: {reverted} genre(s) reverted"
    if missing:
        msg += f", {missing} track(s) not found"
    if deleted_skipped:
        msg += f", {deleted_skipped} deleted track(s) NOT restored (restore from backup)"
    log.info(msg)
    on_status(msg)
