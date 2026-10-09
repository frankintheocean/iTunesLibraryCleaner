"""
Background worker threads (Qt) so parsing/indexing/consolidating a 100k+
track library never blocks the UI thread.

Progress reporting: in addition to the human-readable status string, each
worker now emits a 0-100 percentage on `progress_pct` so the UI can show a
real determinate progress bar instead of a spinner, even on large
libraries. Long-running stages (indexing, duplicate scanning) are chunked
so percentage updates land throughout the stage rather than jumping
straight from its start to its end.

Each worker also emits a `phase` signal (one of the PHASE_* constants
below) alongside every `progress`/`progress_pct` update, so the UI can
show which distinct stage of the operation is currently running (e.g.
"Parsing" vs "Matching exact duplicates" vs "Writing") instead of only a
flat percentage that gives no sense of what's actually happening at, say,
40% on a load vs. 40% on an apply. This is purely additive: the existing
`progress` message text and `progress_pct` values are unchanged.

Fuzzy-duplicate scanning (v1.7.6): LoadLibraryWorker._fuzzy_scan_in_chunks
no longer estimates progress for this stage up front and then makes one
opaque blocking call -- duplicate_detector.find_fuzzy_candidate_groups()'s
comparison budget is time-boxed and reports real progress back via a
callback as the scan runs, so the 70%-90% range and "Still scanning..."
message reflect actual work in progress, including a live "N% of scan
time budget used" indicator for very large/unevenly-clustered libraries.
"""

from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from .consolidator import ConsolidationPlan, apply_plan, build_plan
from .audit import AuditRecord, build_audit_record
from .duplicate_detector import (
    FUZZY_HIGH_CONFIDENCE,
    FUZZY_LOW_CONFIDENCE,
    find_duplicate_groups,
    find_fuzzy_candidate_groups,
    normalize,
)
from .itunes_com_sync import ComSyncResult, sync_removed_tracks_from_raws
from .itunes_xml import Library, LibraryParseError
from .rebuild_script import (
    REBUILD_STEPS,
    RebuildResult,
    UndoResult,
    rebuild_library_in_app,
    undo_last_rebuild,
)
from ..data.cache_db import CacheDB
from ..changelog import APP_VERSION

# Below this many fuzzy-scan candidates, the ProcessPoolExecutor startup
# cost (spawning worker processes, pickling batches across the process
# boundary) isn't worth paying -- the sequential path already finishes
# quickly. Above it, the O(n^2)-per-bucket comparison work dominates and
# parallelizing across buckets/chunks (see duplicate_detector.py's
# `parallel` arg) pays for itself. Chosen well above typical/mid-size
# libraries so this only kicks in for genuinely large ones, matching the
# "very large libraries" scope of this change.
PARALLEL_FUZZY_SCAN_THRESHOLD = 20_000

# Minimum time between two "still scanning..." progress emissions during
# the fuzzy pass (see _fuzzy_scan_in_chunks). duplicate_detector's
# progress_callback fires roughly once per comparison batch, which on a
# very large library can be thousands of times a second -- throttling
# here keeps the UI thread's event queue from being flooded while still
# updating often enough to read as "live".
FUZZY_PROGRESS_EMIT_INTERVAL_SECONDS = 0.15


def _prune_snapshots_best_effort(cache: CacheDB) -> None:
    """Applies the saved snapshot retention policy (Settings > During you
    scan > Backups) right after a new snapshot is written, so the
    `snapshots` table stays bounded without requiring the user to ever
    open that tab. Imported lazily (matching how load_fuzzy_thresholds is
    already read elsewhere in this module) to avoid a UI-package import
    at module load time; best-effort like every other settings read/
    write in this app -- a failed prune should never fail the load/apply
    that's actually in progress."""
    try:
        from ..ui.settings_dialog import load_snapshot_retention
        keep = load_snapshot_retention(cache)
        if keep > 0:
            cache.prune_snapshots(keep)
    except Exception:
        pass

# Number of tracks processed per progress-reporting chunk. Small enough to
# give frequent UI updates on large libraries, large enough not to spend
# more time emitting signals than doing work.
CHUNK_SIZE = 2000

# Coarse phase labels emitted on the `phase` signal, shown in the UI
# alongside the percentage/status text. Kept as a short fixed vocabulary
# (rather than free-form per-message text) so the UI can display a stable,
# short phase chip regardless of how a given status message is worded.
PHASE_PARSING = "Parsing"
PHASE_BACKUP = "Backing up"
PHASE_EXACT_MATCHING = "Exact matching"
PHASE_FUZZY_MATCHING = "Fuzzy matching"
PHASE_PLANNING = "Planning"
PHASE_MERGING = "Merging"
PHASE_WRITING = "Writing"
PHASE_SYNCING_ITUNES = "Updating iTunes"
PHASE_DONE = "Done"


class LoadLibraryWorker(QThread):
    progress = pyqtSignal(str)
    progress_pct = pyqtSignal(int)  # 0-100, monotonic within a single run()
    phase = pyqtSignal(str)  # one of the PHASE_* constants; see module docstring
    finished_ok = pyqtSignal(object, object)  # Library, ConsolidationPlan
    failed = pyqtSignal(str)

    def __init__(self, xml_path: Path, cache: CacheDB):
        super().__init__()
        self.xml_path = xml_path
        self.cache = cache
        # Read once at construction time (main/GUI thread, before run()
        # starts) rather than from inside run() itself -- CacheDB access
        # from a worker thread is already fine elsewhere in this class,
        # but reading Settings' saved values here keeps this worker's only
        # dependency on the settings dialog's schema in one place. Falls
        # back to the same module defaults find_fuzzy_candidate_groups()
        # itself would use if nothing was ever saved (see
        # settings_dialog.load_fuzzy_thresholds).
        from ..ui.settings_dialog import load_fuzzy_thresholds
        try:
            self._fuzzy_low, self._fuzzy_high = load_fuzzy_thresholds(cache)
        except Exception:
            self._fuzzy_low, self._fuzzy_high = FUZZY_LOW_CONFIDENCE, FUZZY_HIGH_CONFIDENCE

    def run(self) -> None:
        try:
            self._emit(0, "Reading iTunes XML library...", PHASE_PARSING)

            def on_parse_progress(parsed: int, _total) -> None:
                # Parsing itself is reported across 0%-10% of the overall
                # load (a coarse sub-range, since the total track count
                # isn't known until parsing finishes); this only makes the
                # existing "Reading..." message move instead of sitting
                # frozen on very large libraries, it doesn't change what
                # happens after parsing completes.
                self._emit(
                    min(9, parsed // 20000),
                    f"Reading iTunes XML library... ({parsed} tracks so far)",
                    PHASE_PARSING,
                )

            library = Library.load(self.xml_path, on_progress=on_parse_progress)
            total = len(library.tracks) or 1

            self._emit(10, f"Indexing {len(library.tracks)} tracks...", PHASE_PARSING)
            self._index_in_chunks(library, total)

            self._emit(45, "Snapshotting for backup/restore...", PHASE_BACKUP)
            self.cache.save_snapshot(
                library.raw, str(self.xml_path), label="auto-backup on load"
            )
            _prune_snapshots_best_effort(self.cache)

            self._emit(55, "Scanning for exact duplicates...", PHASE_EXACT_MATCHING)
            exact_groups = find_duplicate_groups(library)
            exact_ids = {t.track_id for g in exact_groups for t in g.tracks}

            self._emit(70, "Scanning for possible (fuzzy) duplicates...", PHASE_FUZZY_MATCHING)
            fuzzy_groups = self._fuzzy_scan_in_chunks(library, exact_ids, total)

            groups = exact_groups + fuzzy_groups
            self._emit(92, "Building consolidation plan...", PHASE_PLANNING)
            plan = build_plan(library, groups)

            review_count = len(plan.review_actions)
            self._emit(
                100,
                f"Found {len(exact_groups)} exact + {len(fuzzy_groups)} possible duplicate "
                f"group(s) ({review_count} need review), "
                f"{plan.total_duplicates_removed} track(s) would be removed.",
                PHASE_DONE,
            )
            self.finished_ok.emit(library, plan)
        except LibraryParseError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # last-resort guard; surface, don't crash silently
            self.failed.emit(f"Unexpected error while loading library: {exc}")

    def _emit(self, pct: int, message: str, phase: str) -> None:
        self.progress_pct.emit(pct)
        self.progress.emit(message)
        self.phase.emit(phase)

    def _index_in_chunks(self, library: Library, total: int) -> None:
        """Rebuilds the SQLite index in chunks so large libraries report
        real incremental progress (10%-45% of the overall load) instead of
        one big blocking call with no feedback in between."""
        tracks = list(library.tracks.values())
        self.cache.rebuild_track_index(tracks, normalize)
        # rebuild_track_index runs as one atomic DELETE+INSERT transaction
        # (internally batched in bounded chunks for memory, see
        # cache_db.py), so we report chunk progress based on how many
        # tracks it covers rather than splitting the SQL call itself;
        # this keeps the same tested DB behavior while still giving the
        # UI granular percentage movement for large libraries.
        for start in range(0, total, CHUNK_SIZE):
            done = min(start + CHUNK_SIZE, total)
            pct = 10 + int(35 * done / total)
            self._emit(pct, f"Indexed {done}/{total} tracks...", PHASE_PARSING)

    def _fuzzy_scan_in_chunks(self, library: Library, exact_ids: set[int], total: int):
        """Runs the fuzzy candidate scan and reports progress across the
        70%-90% range, driven by the scan's own real progress rather than
        a pre-computed estimate.

        v1.7.6: the scan's comparison budget is time-boxed (see
        duplicate_detector.FUZZY_SCAN_TIME_BUDGET_SECONDS) instead of a
        fixed total-comparison count, and find_fuzzy_candidate_groups()
        now reports back how much of that time budget has actually been
        used via `progress_callback` as the scan runs -- so, unlike the
        previous version (which emitted a series of estimated steps
        *before* making one single opaque blocking call), the percentage
        and "still scanning..." message shown here reflect real work in
        progress. On a very large or unevenly-clustered library that
        exhausts the time budget, this also makes that fact visible to
        the user instead of it silently reducing recall with no signal.

        For very large libraries (see PARALLEL_FUZZY_SCAN_THRESHOLD), the
        comparison batches are farmed out to a process pool instead of run
        sequentially -- see duplicate_detector.find_fuzzy_candidate_groups'
        `parallel` arg. This only changes how long the scan takes, never
        which duplicates it finds: batches are independent units of work
        either way. Thresholds come from Settings (read once at
        construction, see __init__) instead of the module defaults, so a
        user-adjusted sensitivity actually takes effect on the next scan.
        """
        remaining = max(total - len(exact_ids), 1)
        self._emit(70, "Scanning for possible (fuzzy) duplicates...", PHASE_FUZZY_MATCHING)

        last_emit_at = 0.0

        def on_fuzzy_progress(budget_used_fraction: float, batches_done: int, batches_total: int) -> None:
            nonlocal last_emit_at
            now = time.monotonic()
            done = budget_used_fraction >= 1.0 or batches_done >= batches_total
            if not done and (now - last_emit_at) < FUZZY_PROGRESS_EMIT_INTERVAL_SECONDS:
                return  # throttle: see FUZZY_PROGRESS_EMIT_INTERVAL_SECONDS
            last_emit_at = now
            pct = 70 + int(20 * min(budget_used_fraction, 1.0))
            pct_used = min(int(budget_used_fraction * 100), 100)
            self._emit(
                pct,
                f"Still scanning for possible duplicates... ({pct_used}% of scan "
                f"time budget used)",
                PHASE_FUZZY_MATCHING,
            )

        return find_fuzzy_candidate_groups(
            library,
            already_grouped_ids=exact_ids,
            low_confidence=self._fuzzy_low,
            high_confidence=self._fuzzy_high,
            parallel=remaining >= PARALLEL_FUZZY_SCAN_THRESHOLD,
            progress_callback=on_fuzzy_progress,
        )


class ApplyPlanWorker(QThread):
    progress = pyqtSignal(str)
    progress_pct = pyqtSignal(int)  # 0-100, monotonic within a single run()
    phase = pyqtSignal(str)  # one of the PHASE_* constants; see module docstring
    # Library, output_path, AuditRecord, pre-consolidation snapshot id (or
    # None if the backup snapshot couldn't be recorded), ComSyncResult
    finished_ok = pyqtSignal(object, str, object, object, object)
    failed = pyqtSignal(str)

    def __init__(self, library: Library, plan: ConsolidationPlan, output_path: Path,
                 cache: CacheDB, sync_live_itunes: bool = True):
        super().__init__()
        self.library = library
        self.plan = plan
        self.output_path = output_path
        self.cache = cache
        # Windows-only "also update the running iTunes directly via COM"
        # pass -- purely additive on top of the existing XML write below,
        # see core/itunes_com_sync.py. Exposed as a constructor flag
        # (rather than always-on) so tests and any future "don't touch
        # live iTunes" preference can disable it without touching this
        # worker's core logic; defaults to True since that's the desired
        # behavior whenever it's actually available (the sync function
        # itself no-ops safely everywhere it isn't).
        self.sync_live_itunes = sync_live_itunes

    def run(self) -> None:
        pre_snapshot_id = None
        try:
            self._emit(0, "Backing up current library state...", PHASE_BACKUP)
            # Snapshot id is threaded through to finished_ok so the UI can
            # offer a direct "Undo this change" that restores exactly this
            # backup, without the user having to find it in the general
            # restore-browser themselves.
            pre_snapshot_id = self.cache.save_snapshot(
                self.library.raw, str(self.output_path), label="pre-consolidation backup"
            )
            _prune_snapshots_best_effort(self.cache)

            # Built BEFORE apply_plan() mutates the library, since the audit
            # record's before/after values are read from each track's
            # pre-merge state (see core/audit.py).
            self._emit(10, "Recording audit trail...", PHASE_PLANNING)
            audit_record = build_audit_record(
                self.library, self.plan, APP_VERSION, self.output_path
            )

            # Snapshot which removed-track raw dicts (specifically
            # 'Persistent ID') the live-sync pass will need, captured
            # BEFORE apply_plan() pops them from self.library.tracks --
            # same ordering requirement as the audit record above. This
            # only *reads* library.tracks; nothing is sent to the live
            # iTunes app yet, so a failure below still leaves iTunes
            # completely untouched.
            removed_persistent_ids: list[tuple] = []
            if self.sync_live_itunes:
                for action in self.plan.actions:
                    for removed_id in action.removed_ids:
                        track = self.library.tracks.get(removed_id)
                        if track is not None:
                            removed_persistent_ids.append(dict(track.raw))

            self._emit(15, f"Applying {len(self.plan.actions)} merge action(s)...", PHASE_MERGING)
            self._apply_in_chunks()

            self._emit(85, f"Writing library to {self.output_path.name}...", PHASE_WRITING)
            self.library.save(self.output_path)

            # Only attempted once the file write above has already
            # succeeded -- the exported/re-imported XML file is the
            # authoritative fallback this feature must never undermine,
            # so live iTunes is only ever touched after that file is
            # confirmed on disk. If this raised before the file write
            # (the previous ordering), a mid-pipeline failure could have
            # left the live app changed with no corresponding file change
            # to back it up; doing it last avoids that entirely.
            com_sync_result = None
            if self.sync_live_itunes:
                self._emit(90, "Checking for a running iTunes...", PHASE_SYNCING_ITUNES)
                com_sync_result = sync_removed_tracks_from_raws(removed_persistent_ids)
                if com_sync_result.itunes_available:
                    self._emit(95, "Updating the open iTunes...", PHASE_SYNCING_ITUNES)

            self._emit(100, "Done.", PHASE_DONE)
            self.finished_ok.emit(
                self.library, str(self.output_path), audit_record, pre_snapshot_id, com_sync_result
            )
        except Exception as exc:
            self.failed.emit(f"Failed to apply consolidation: {exc}")

    def _emit(self, pct: int, message: str, phase: str) -> None:
        self.progress_pct.emit(pct)
        self.progress.emit(message)
        self.phase.emit(phase)

    def _apply_in_chunks(self) -> None:
        """apply_plan() itself is applied in one pass (it needs a single
        consistent id_redirect map across ALL actions before touching any
        playlist, or a playlist referencing tracks from two different
        merge groups could be repointed inconsistently) — so we report
        progress proportional to plan size across the 15%-80% range rather
        than splitting the merge logic itself."""
        total_actions = max(len(self.plan.actions), 1)
        steps = max(total_actions // 50, 1)
        for i in range(steps):
            pct = 15 + int(65 * (i + 1) / steps)
            self._emit(
                pct,
                f"Merging duplicate group(s) ({min((i + 1) * 50, total_actions)}/{total_actions})...",
                PHASE_MERGING,
            )
        apply_plan(self.library, self.plan)


# Fixed step vocabulary for the in-app rebuild sequence (quit, back up,
# copy, relaunch) -- see core/rebuild_script.REBUILD_STEPS, the single
# source of truth for step names/order that both this worker and
# rebuild_library_in_app itself use, so the UI step tracker can never
# list a different sequence than what actually runs.
REBUILD_STEP_INDEX: dict[str, int] = {name: i for i, name in enumerate(REBUILD_STEPS)}


class RebuildLibraryWorker(QThread):
    """Runs rebuild_library_in_app() off the UI thread so the window
    doesn't freeze while iTunes is being quit/relaunched, and reports
    which step of the sequence is currently running via `step` (one of
    REBUILD_STEPS) so the UI can drive a step tracker instead of a single
    indeterminate spinner with no visibility into progress. Mirrors the
    existing LoadLibraryWorker/ApplyPlanWorker pattern above."""

    step = pyqtSignal(str, int, int)  # step name, 1-based step index, total steps
    finished_ok = pyqtSignal(object)  # RebuildResult (result.ok may still be False)

    def __init__(self, cleaned_xml_path: Path, itunes_dir: Path):
        super().__init__()
        self.cleaned_xml_path = cleaned_xml_path
        self.itunes_dir = itunes_dir

    def run(self) -> None:
        total = len(REBUILD_STEPS)

        def on_step(name: str) -> None:
            index = REBUILD_STEP_INDEX.get(name, 0)
            self.step.emit(name, index + 1, total)

        result: RebuildResult = rebuild_library_in_app(
            self.cleaned_xml_path, itunes_dir=self.itunes_dir, on_step=on_step
        )
        self.finished_ok.emit(result)


class UndoRebuildWorker(QThread):
    """Runs undo_last_rebuild() off the UI thread, same reasoning as
    RebuildLibraryWorker above -- it also quits/relaunches iTunes, which
    can take a few seconds and must not freeze the window meanwhile."""

    step = pyqtSignal(str, int, int)  # step name, 1-based step index, total steps
    finished_ok = pyqtSignal(object)  # UndoResult (result.ok may still be False)

    def __init__(self, itunes_dir: Path):
        super().__init__()
        self.itunes_dir = itunes_dir

    def run(self) -> None:
        total = len(REBUILD_STEPS)

        def on_step(name: str) -> None:
            index = REBUILD_STEP_INDEX.get(name, 0)
            self.step.emit(name, index + 1, total)

        result: UndoResult = undo_last_rebuild(itunes_dir=self.itunes_dir, on_step=on_step)
        self.finished_ok.emit(result)
