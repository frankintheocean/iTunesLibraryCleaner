"""
SQLite-backed cache/index.

Purpose:
  - Fast indexed lookup of tracks by normalized (artist, title) without
    re-scanning the whole in-memory dict on every operation -- matters at
    100k+ track scale.
  - Backup/restore: every load of a library file is snapshotted here first,
    so a bad consolidation run can be undone by restoring the last snapshot
    -- independent of whatever the OS file system is doing.

This is a cache/index, not the source of truth. iTunes' own XML library
file remains authoritative, per product requirement; this DB only helps
us search and undo faster.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# iTunes/Apple Music plists represent dates as native Python `datetime`
# objects (via plistlib's <date> type). JSON has no date type, so snapshots
# must tag datetimes on the way in and restore them on the way out --
# otherwise a restored library round-trips every <date> field into a plain
# <string>, which iTunes/Apple Music will not accept as a valid date on
# reimport. This marker wraps ISO-8601 strings that came from a datetime so
# the loader can tell them apart from ordinary string fields.
_DATETIME_MARKER = "__pydatetime_iso__"


def _json_default(obj):
    if isinstance(obj, datetime):
        return {_DATETIME_MARKER: obj.isoformat()}
    return str(obj)


def _json_object_hook(d: dict):
    iso = d.get(_DATETIME_MARKER)
    if iso is not None and len(d) == 1:
        # Bug fix: both plistlib.load() and this app's own streaming
        # parser (core/plist_stream.py, built to match plistlib exactly)
        # produce naive datetimes for plist <date> fields -- there is no
        # implicit UTC tzinfo to restore. Round-trip the value exactly as
        # stored (isoformat() on a naive datetime has no offset suffix, so
        # fromisoformat() here already reconstructs the same naive value)
        # rather than forcing tzinfo=utc, which previously changed a
        # restored library's dates from naive to aware -- a shape no
        # freshly-loaded library ever has, and something a naive/aware
        # comparison or min()/max() elsewhere in the app could choke on if
        # a restored track were ever mixed with a freshly-parsed one.
        return datetime.fromisoformat(iso)
    return d

SCHEMA = """
CREATE TABLE IF NOT EXISTS track_index (
    track_id INTEGER PRIMARY KEY,
    norm_artist TEXT NOT NULL,
    norm_title TEXT NOT NULL,
    duration_ms INTEGER,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_track_artist_title ON track_index(norm_artist, norm_title);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    source_path TEXT NOT NULL,
    label TEXT,
    library_json TEXT NOT NULL,
    checksum TEXT
);

-- Small persisted key/value store for UI state that should survive
-- between sessions (window geometry, duplicates-table column widths,
-- last-used filter text/tier). Deliberately generic (one row per key,
-- JSON-encoded value) rather than one bespoke table per setting, since
-- this is UI preference data, not anything that needs querying/indexing.
CREATE TABLE IF NOT EXISTS ui_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

-- One lightweight row per library-health scan (see
-- MainWindow._record_health_snapshot_stats, called from _refresh_health),
-- feeding the Library Health tab's growth/duplicate-accumulation
-- timeline. Deliberately separate from `snapshots` above: that table
-- stores a full library_json blob per backup (expensive to re-parse just
-- to plot a trend line, and only written on load/apply, not on every
-- health refresh e.g. after a manual review edit), whereas this is just
-- a handful of small integers, cheap to write often and cheap to read
-- back for a chart. Never used for restore -- `snapshots` remains the
-- only backup/restore source of truth.
CREATE TABLE IF NOT EXISTS health_snapshot_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    source_path TEXT NOT NULL,
    track_count INTEGER NOT NULL,
    duplicate_track_count INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_health_stats_created_at ON health_snapshot_stats(created_at);
"""


class SnapshotIntegrityError(Exception):
    """Raised by CacheDB.load_snapshot when a stored backup snapshot fails
    its integrity check -- either its SHA-256 checksum (recorded at
    save_snapshot time, see the `checksum` column) no longer matches the
    stored bytes, or the stored library_json can't even be parsed back
    (e.g. truncated by a crash mid-write, disk corruption, or a
    hand-edited cache file).

    Kept as its own exception type, distinct from the existing KeyError
    load_snapshot already raises for "no snapshot with this id", so a
    caller -- see ui/main_window._restore_snapshot_by_id -- can tell "this
    backup doesn't exist" apart from "this backup exists but is corrupted"
    and show an accurate message for each, rather than silently handing
    back (or restoring) whatever a corrupted row happens to decode into.
    """


class CacheDB:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: this instance is created on the GUI
        # thread but its methods are also called from LoadLibraryWorker
        # and ApplyPlanWorker, which run on separate QThreads. A single
        # sqlite3 connection is otherwise pinned to the thread that
        # created it and raises ProgrammingError from any other thread.
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")  # safer for larger writes
        # sqlite3 connections allow being *handed between* threads
        # (that's what check_same_thread=False relaxes) but are still not
        # safe for *concurrent* use from multiple threads at once. A
        # worker thread's load/apply calls and the GUI thread's UI-state
        # save (e.g. on window close, or a snapshot-restore mid-load)
        # could otherwise interleave against the same connection. This
        # lock serializes every cursor use across all threads. Created
        # before the schema/migration calls just below (rather than
        # after, as before) since both of those now also take it.
        self._lock = threading.Lock()
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._ensure_snapshot_checksum_column()

    def _ensure_snapshot_checksum_column(self) -> None:
        """Migration for cache DBs created before the `checksum` column
        existed (v1.9.0-pre). `CREATE TABLE IF NOT EXISTS` in SCHEMA above
        only creates the column on a brand-new DB file -- it's a no-op
        against an existing `snapshots` table from an earlier app version,
        so that column has to be added here explicitly, once, if missing.
        Existing rows get `checksum = NULL`, which load_snapshot treats as
        "no baseline to verify against" (see its docstring) rather than a
        failure, so upgrading never makes previously-saved backups
        unrestorable."""
        with self._lock:
            cur = self._conn.execute("PRAGMA table_info(snapshots);")
            columns = {row[1] for row in cur.fetchall()}
            if "checksum" not in columns:
                self._conn.execute("ALTER TABLE snapshots ADD COLUMN checksum TEXT;")
                self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _cursor(self):
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                cur.close()

    # ---- track index (fast lookup / search) --------------------------------

    # Rows are inserted in batches rather than building one Python list of
    # every row's JSON up front (the previous behavior). At 100k+ tracks,
    # materializing every row's json.dumps() output simultaneously before
    # the first executemany() adds tens of MB of peak memory on top of the
    # already-loaded library, for no benefit -- executemany() consumes an
    # iterable, so it doesn't need every row ready at once. Batch size is
    # a memory/throughput tradeoff, not a correctness knob; the resulting
    # index contents are identical either way.
    _INDEX_BATCH_SIZE = 5000

    def rebuild_track_index(self, tracks, normalize_fn) -> None:
        """tracks: iterable of Track objects. Rebuilds the index from scratch
        -- cheap enough at 100k rows and avoids drift bugs from incremental
        updates. Uses executemany (in bounded batches) for throughput."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM track_index;")
            batch = []
            for t in tracks:
                batch.append((
                    t.track_id,
                    normalize_fn(t.artist),
                    normalize_fn(t.name),
                    t.total_time_ms,
                    json.dumps(t.raw, default=_json_default),
                ))
                if len(batch) >= self._INDEX_BATCH_SIZE:
                    cur.executemany(
                        "INSERT INTO track_index (track_id, norm_artist, norm_title, duration_ms, raw_json) "
                        "VALUES (?, ?, ?, ?, ?)",
                        batch,
                    )
                    batch.clear()
            if batch:
                cur.executemany(
                    "INSERT INTO track_index (track_id, norm_artist, norm_title, duration_ms, raw_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    batch,
                )

    def find_by_artist_title(self, norm_artist: str, norm_title: str) -> list[dict]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT raw_json FROM track_index WHERE norm_artist=? AND norm_title=?",
                (norm_artist, norm_title),
            )
            return [json.loads(r[0], object_hook=_json_object_hook) for r in cur.fetchall()]

    def track_count(self) -> int:
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM track_index;")
            return cur.fetchone()[0]

    # ---- backup / restore ---------------------------------------------------

    def save_snapshot(self, library_raw: dict, source_path: str, label: str = "") -> int:
        library_json = json.dumps(library_raw, default=_json_default)
        # SHA-256 of the exact bytes written to `library_json`, checked
        # back against those same bytes on restore (see load_snapshot) so
        # a corrupted row (partial write, disk bit-rot, hand-edited cache
        # file) is caught before it's ever handed back as if it were a
        # good backup.
        checksum = hashlib.sha256(library_json.encode("utf-8")).hexdigest()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO snapshots (created_at, source_path, label, library_json, checksum) "
                "VALUES (?, ?, ?, ?, ?)",
                (time.time(), source_path, label, library_json, checksum),
            )
            return cur.lastrowid

    def list_snapshots(self) -> list[dict]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT id, created_at, source_path, label FROM snapshots ORDER BY created_at DESC;"
            )
            return [
                {"id": r[0], "created_at": r[1], "source_path": r[2], "label": r[3]}
                for r in cur.fetchall()
            ]

    def load_snapshot(self, snapshot_id: int) -> dict:
        """Returns the rehydrated library dict for `snapshot_id`, having
        first verified the stored data's integrity -- so a caller (see
        ui/main_window._restore_snapshot_by_id) can never be handed
        corrupted data to restore from without knowing it.

        Two independent checks, both raising SnapshotIntegrityError
        (never returning a partial/wrong result silently):
          1. If a checksum was recorded at save time (every snapshot
             saved by this version or later), the stored library_json's
             SHA-256 must still match it exactly.
          2. The stored library_json must still parse as valid JSON --
             catches corruption a checksum mismatch would also catch, but
             kept as an explicit check too so the failure message is
             clear even if checksum verification is ever bypassed.

        Snapshots saved before the `checksum` column existed have
        `checksum IS NULL` -- treated as "no baseline to verify against"
        rather than a failure, so upgrading this app never makes an
        older, previously-trustworthy backup suddenly unrestorable.
        """
        with self._cursor() as cur:
            cur.execute(
                "SELECT library_json, checksum FROM snapshots WHERE id=?;", (snapshot_id,)
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(f"No snapshot with id {snapshot_id}")
        library_json, stored_checksum = row
        if stored_checksum:
            actual_checksum = hashlib.sha256(library_json.encode("utf-8")).hexdigest()
            if actual_checksum != stored_checksum:
                raise SnapshotIntegrityError(
                    f"Backup snapshot {snapshot_id} failed its integrity check "
                    "(checksum mismatch) -- the stored backup data no longer "
                    "matches what was originally saved and may be corrupted. "
                    "Restore was stopped before writing anything."
                )
        try:
            return json.loads(library_json, object_hook=_json_object_hook)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SnapshotIntegrityError(
                f"Backup snapshot {snapshot_id} is corrupted and can't be read "
                f"back ({exc}). Restore was stopped before writing anything."
            ) from exc

    def delete_snapshot(self, snapshot_id: int) -> None:
        with self._cursor() as cur:
            cur.execute("DELETE FROM snapshots WHERE id=?;", (snapshot_id,))

    def snapshot_count(self) -> int:
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM snapshots;")
            return cur.fetchone()[0]

    # Retention policy: this DB is a cache/index, not the source of truth
    # (see module docstring) -- every load and every apply writes a new
    # full-library-JSON snapshot (see workers.py), so left unmanaged this
    # table grows without bound on a machine that's used regularly.
    # Pruning only ever deletes the *oldest* rows past a kept count, never
    # touches track_index/ui_settings/health_snapshot_stats, and is always
    # explicit (a max-to-keep count passed in) rather than time-based, so
    # "how many backups do I have" stays predictable regardless of how
    # often the app happens to be used.
    def prune_snapshots(self, keep: int) -> int:
        """Deletes the oldest snapshots beyond the most recent `keep`,
        newest-first (matching list_snapshots' ordering). `keep <= 0`
        means unlimited -- nothing is deleted, so "0" reads naturally as
        "no cap" rather than "delete everything". Returns the number of
        rows deleted."""
        if keep <= 0:
            return 0
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM snapshots WHERE id IN ("
                "  SELECT id FROM snapshots ORDER BY created_at DESC "
                "  LIMIT -1 OFFSET ?"
                ");",
                (keep,),
            )
            return cur.rowcount if cur.rowcount is not None and cur.rowcount > 0 else 0

    # ---- health-stats history (growth/duplicate-accumulation timeline) ----

    # Cap on how often a stats row is recorded for the *same* source
    # library within a short window, so opening the Health tab repeatedly
    # in one sitting (or every manual-review edit re-running
    # _refresh_health) doesn't flood this table with near-duplicate
    # points that would all land on the same spot on the timeline anyway.
    # Applied by the caller (see MainWindow._record_health_snapshot_stats)
    # via record_health_snapshot's `min_interval_seconds`, not enforced
    # here, since only the caller knows what "the same scan" means for its
    # own call pattern.
    def record_health_snapshot(
        self,
        source_path: str,
        track_count: int,
        duplicate_track_count: int,
        min_interval_seconds: float = 0.0,
    ) -> None:
        """Appends one (timestamp, track_count, duplicate_track_count) row
        for `source_path`. If `min_interval_seconds` > 0 and the most
        recent existing row for this exact source_path is newer than that
        interval, this updates that row in place instead of inserting a
        new one -- so rapid repeat scans of the same library (e.g. several
        manual-review edits in a row) move one point forward rather than
        plotting a dense cluster of them."""
        now = time.time()
        with self._cursor() as cur:
            if min_interval_seconds > 0:
                cur.execute(
                    "SELECT id, created_at FROM health_snapshot_stats "
                    "WHERE source_path=? ORDER BY created_at DESC LIMIT 1;",
                    (source_path,),
                )
                row = cur.fetchone()
                if row is not None and (now - row[1]) < min_interval_seconds:
                    cur.execute(
                        "UPDATE health_snapshot_stats SET created_at=?, "
                        "track_count=?, duplicate_track_count=? WHERE id=?;",
                        (now, track_count, duplicate_track_count, row[0]),
                    )
                    return
            cur.execute(
                "INSERT INTO health_snapshot_stats "
                "(created_at, source_path, track_count, duplicate_track_count) "
                "VALUES (?, ?, ?, ?);",
                (now, source_path, track_count, duplicate_track_count),
            )

    def list_health_snapshots(self, limit: int = 500) -> list[dict]:
        """Returns up to `limit` recorded points, oldest first (the order
        a timeline chart wants to draw them in), across every library this
        app has ever scanned -- the Health tab's timeline distinguishes
        libraries by source_path/label itself if it needs to; this is a
        simple full history read."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT created_at, source_path, track_count, duplicate_track_count "
                "FROM health_snapshot_stats ORDER BY created_at ASC LIMIT ?;",
                (limit,),
            )
            return [
                {
                    "created_at": r[0],
                    "source_path": r[1],
                    "track_count": r[2],
                    "duplicate_track_count": r[3],
                }
                for r in cur.fetchall()
            ]

    # ---- UI settings (window geometry, column widths, last filter) ---------

    def get_setting(self, key: str, default=None):
        """Returns the JSON-decoded value stored under `key`, or `default`
        if it isn't present or the stored JSON is corrupt (e.g. hand-edited
        or from an incompatible future version) -- a bad/missing setting
        should never prevent the app from starting, only fall back to a
        sane default silently."""
        with self._cursor() as cur:
            cur.execute("SELECT value_json FROM ui_settings WHERE key=?;", (key,))
            row = cur.fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except (TypeError, ValueError, json.JSONDecodeError):
            return default

    def set_setting(self, key: str, value) -> None:
        """Upserts a single JSON-serializable UI setting. `value=None` is
        allowed and stored as JSON null (distinct from the key not existing
        at all), so callers can round-trip an intentionally-empty filter
        string, etc."""
        payload = json.dumps(value)
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO ui_settings (key, value_json) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json;",
                (key, payload),
            )
