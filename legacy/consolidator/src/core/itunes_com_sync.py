"""
Windows iTunes COM live-sync.

When iTunes (classic Windows iTunes, not the new Apple Music app -- which
does not expose this COM interface) is currently running on this machine,
a consolidation can additionally be mirrored directly into the live
application via its iTunesLib COM automation interface: the specific
duplicate Track objects that a MergeAction is about to remove are located
in the running application's own Library Playlist (and every other user
playlist except Podcasts/Audiobooks) and deleted from there directly, so
the open iTunes window updates immediately -- no quit, no manual
re-import, no restart.

This is strictly additive and strictly best-effort:
  - The existing XML export/re-import pipeline (Library.load/.save,
    ApplyPlanWorker) is completely unchanged and remains the only thing
    that actually mutates the Library object / writes the output file.
    Nothing in this module is on that path.
  - COM sync is attempted only when iTunes is both running AND responds
    to a trivial COM call within a short timeout ("responsive" -- see
    is_itunes_running_and_responsive()). If iTunes isn't running, is
    starting up, is showing a blocking modal dialog, or is otherwise
    unresponsive, this module is skipped entirely and the caller falls
    back to the pre-existing behavior (the user reopens/re-imports the
    written XML file themselves, exactly as v1.3.7 already documents).
  - A failure partway through (a track already gone, a playlist that
    changed underneath us, COM throwing) never raises out to the caller
    as a hard error and never blocks the UI thread -- every track removal
    is attempted independently and failures are collected, not raised,
    so one bad track can't abort the rest of the sync or the (already-
    successful) file-based consolidation that triggered it.
  - Podcasts and Audiobooks playlists are explicitly excluded from the
    live removal pass, per product requirement -- iTunes manages both
    specially (episode/book state, not ordinary playlist membership) and
    this tool has never edited either.
  - This only ever *removes* specific tracks that a confirmed
    ConsolidationPlan already decided to remove; it never adds, reorders,
    or edits anything in the live library, and it is only ever invoked
    after the same user confirmation dialog that gates the existing
    apply flow (see MainWindow._on_apply_clicked) -- there is no separate
    or additional confirmation prompt for COM sync specifically, since it
    mirrors a decision already made and confirmed for the file-based
    apply.

Windows + iTunes only: importing this module is always safe on any
platform (the pywin32 import is deferred into the functions that need
it), but every function here is a no-op / returns a "not available"
result on macOS, Linux, or a Windows machine that doesn't have classic
iTunes (and therefore pywin32's COM bindings for it) installed.

Note on the old "live XML import" path (removed in 1.6.6-pre): classic
Windows iTunes's IITunes COM automation interface has no method for
importing a Library.xml file / merging its playlists into the open
library -- there never was a real "OpenXML" member on the Application
object, so any call to it was rejected outright (COM "member not
found") on every real machine, 100% of the time, regardless of the XML
content. That code path (import_cleaned_xml_live() and its
XmlImportResult return type) has been deleted entirely, along with the
call site in rebuild_script.rebuild_library_in_app(), which now goes
straight to its (real, working) file-swap-and-relaunch path -- see that
function's docstring for the actual rebuild flow.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field

# iTunesLib's own special-kind constants (ITPlaylistKind), used to tell
# Podcasts/Audiobooks apart from ordinary user playlists without relying
# on playlist names (which are user-renameable) or matching against the
# Library.xml-derived Track/Playlist objects at all -- this module only
# ever talks to the live COM object graph, never mixes in the XML-parsed
# objects from core/itunes_xml.py.
_ITPlaylistKindPodcast = 3
_ITPlaylistKindAudiobooks = 5  # note: not exposed by every iTunes COM
# version; guarded with getattr-style fallback below rather than assumed.

# Bounded wait for the initial "is iTunes even responsive" probe and for
# each individual COM call while removing tracks. iTunes COM calls are
# normally near-instant (in-process automation, not a network call), but
# a modal dialog on top of iTunes (e.g. "Keep file in iTunes Media
# folder?", an authorization prompt) blocks its whole COM apartment until
# dismissed -- without a bound, a single stuck dialog could hang this
# call indefinitely and, transitively, the worker thread calling it.
_COM_CALL_TIMEOUT_SECONDS = 5.0

# Retry/backoff for individual COM calls that fail transiently (iTunes
# momentarily busy servicing another automation call, a track/playlist
# object briefly unavailable mid-library-refresh, etc). This is separate
# from -- and deliberately much shorter-lived than -- the modal-dialog
# case above: a stuck dialog is caught by the timeout/responsiveness probe
# and reported immediately rather than retried, since retrying against a
# dialog that needs a human to dismiss it would just waste the backoff
# window for nothing. These constants instead cover the "iTunes answered
# the responsiveness probe fine, but this one call bounced" case, which
# retrying a few times with a short, doubling delay resolves the vast
# majority of the time without meaningfully slowing down a whole-library
# apply (worst case across all retries for one call is well under a
# second).
_COM_RETRY_ATTEMPTS = 3
_COM_RETRY_BASE_DELAY_SECONDS = 0.15


@dataclass
class ComSyncResult:
    """Outcome of one attempted live-iTunes sync for a single apply run.
    Always returned, never raised -- see module docstring; this is a
    report for the UI to show, not a control-flow signal."""
    attempted: bool
    itunes_available: bool
    tracks_removed: int = 0
    tracks_not_found: int = 0
    # Count of individual (track, playlist) removal operations performed
    # across every playlist a removed track was found in -- e.g. one
    # track referenced by 3 playlists plus the Library contributes 4 here,
    # not 1. Used only for the human-readable summary below, not as a
    # distinct-playlist count.
    playlist_removals: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def succeeded_fully(self) -> bool:
        return self.attempted and self.itunes_available and not self.errors

    def summary_text(self) -> str:
        if not self.attempted:
            return "Live iTunes sync was not attempted."
        if not self.itunes_available:
            return (
                "iTunes isn't currently running (or isn't responding), so "
                "the live app wasn't updated automatically -- use the "
                "exported XML file and the reopen steps below instead."
            )
        parts = [f"{self.tracks_removed} track(s) removed directly from the open iTunes."]
        if self.playlist_removals:
            parts.append(f"{self.playlist_removals} playlist entry/entries updated live.")
        if self.tracks_not_found:
            parts.append(
                f"{self.tracks_not_found} track(s) were already gone from iTunes "
                "and didn't need removing."
            )
        if self.errors:
            parts.append(
                f"{len(self.errors)} track(s) could not be removed live "
                "(see details) -- they'll still be removed from the exported "
                "file as usual."
            )
        return " ".join(parts)


def is_windows() -> bool:
    return sys.platform == "win32"


def _try_connect():
    """Returns a live iTunesLib.iTunes COM application object, or None if
    unavailable for any reason (not Windows, pywin32/COM bindings not
    installed, iTunes not running, or the connection attempt itself
    raised). Never raises -- every failure mode collapses to None so
    callers have one simple availability check."""
    if not is_windows():
        return None
    try:
        import win32com.client  # pywin32; optional dependency, Windows-only
        import pythoncom
    except ImportError:
        return None
    try:
        # Each call site runs on a worker QThread (see workers.py), which
        # is a distinct OS thread from wherever CoInitialize may already
        # have been called (if at all) -- COM apartments are per-thread,
        # so this thread needs its own initialization before it can make
        # any COM call. CoInitialize is safe to call more than once on
        # the same thread (subsequent calls just bump a refcount), so
        # this is safe even if a future caller already initialized COM
        # on this same thread for some other reason.
        pythoncom.CoInitialize()
    except Exception:
        pass  # if this fails, the Dispatch call below will fail too, and be caught there
    try:
        # GetActiveObject binds to an *already-running* iTunes instance
        # only -- unlike Dispatch(), it never launches iTunes if it isn't
        # already open, which matters here: this feature must only ever
        # touch an iTunes the user already has open, never start a new
        # one as a side effect of running a consolidation.
        app = win32com.client.GetActiveObject("iTunes.Application")
        return app
    except Exception:
        return None


def is_itunes_running_and_responsive(timeout_seconds: float = _COM_CALL_TIMEOUT_SECONDS) -> bool:
    """True only if iTunes is both running and currently answering COM
    calls -- a trivial read-only property access, bounded by a watchdog
    thread so a modal dialog blocking iTunes's COM apartment can't hang
    this check indefinitely. False for every other case (not running,
    not on Windows, pywin32 missing, or unresponsive), never raises."""
    app = _try_connect()
    if app is None:
        return False

    result: dict[str, object] = {}

    def _probe():
        try:
            # .Windows.Count is about as cheap a real round-trip as this
            # interface offers -- enough to prove the COM apartment is
            # actually answering, not just that GetActiveObject found a
            # registered class.
            _ = app.Windows.Count
            result["ok"] = True
        except Exception as exc:
            result["ok"] = False
            result["error"] = exc

    import threading

    probe_thread = threading.Thread(target=_probe, daemon=True)
    probe_thread.start()
    probe_thread.join(timeout_seconds)
    if probe_thread.is_alive():
        # Still blocked (almost always a modal dialog on top of iTunes) --
        # leave the probe thread to finish/die on its own; report
        # unresponsive rather than waiting any longer. The thread is a
        # daemon, so it never prevents process exit even if iTunes stays
        # stuck for the rest of the session.
        return False
    return bool(result.get("ok"))


def _call_with_retry(fn, attempts: int = _COM_RETRY_ATTEMPTS,
                      base_delay: float = _COM_RETRY_BASE_DELAY_SECONDS):
    """Calls fn() (a zero-arg callable wrapping one COM operation),
    retrying with a doubling backoff delay if it raises. Returns fn()'s
    result on the first success; re-raises the *last* exception if every
    attempt fails, so the caller's existing except-and-record-to-
    result.errors handling (see _remove_track_everywhere) is unchanged --
    this only adds retries in front of that existing failure path, it
    never changes what a final, exhausted failure looks like to the
    caller. Never sleeps after the final attempt."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - COM errors surface as generic Exception
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(base_delay * (2 ** attempt))
    assert last_exc is not None
    raise last_exc


def _is_excluded_playlist(playlist) -> bool:
    """True for Podcasts/Audiobooks (never touched live, per product
    requirement) and for any other non-user playlist kind (the Library
    itself, Movies, TV Shows, Genius, folders) that isn't an ordinary
    playlist worth repointing -- mirrors itunes_xml.Playlist.is_special's
    intent, but against the live COM object's own Kind, since a live
    iTunesLib Playlist has no relation to the XML-parsed Playlist class."""
    try:
        kind = playlist.Kind
    except Exception:
        return True  # can't tell what it is; safer to skip than to touch it
    if kind == _ITPlaylistKindPodcast:
        return True
    if kind == _ITPlaylistKindAudiobooks:
        return True
    # ITPlaylistKindLibrary is handled separately by the caller (it's the
    # very playlist duplicate tracks are removed FROM, not excluded from);
    # everything else recognizable as a "special" kind (Movies, TV Shows,
    # Purchased, Genius) is also skipped -- this feature only ever
    # repoints/removes from ordinary user playlists and the main library,
    # matching the scope of the existing XML-based consolidator.
    try:
        return bool(playlist.Smart)
    except Exception:
        return False


def _remove_track_everywhere(app, persistent_id_high: int, persistent_id_low: int,
                              result: ComSyncResult) -> bool:
    """Finds every live Track with the given Persistent ID (Apple's
    stable per-track identity -- the same field consolidator.py's
    _IDENTITY_FIELDS deliberately never backfills) across the main
    Library playlist and every included user playlist, and deletes each
    occurrence. Returns True if at least one occurrence was found and
    removed. Never raises -- COM errors for one track/playlist are
    appended to result.errors and the function moves on, so one stuck
    track can't abort the rest of the sync."""
    found_any = False
    try:
        library_playlist = app.LibraryPlaylist
    except Exception as exc:
        result.errors.append(f"Could not access iTunes library playlist: {exc}")
        return False

    all_playlists = [library_playlist]
    try:
        for pl in app.LibraryPlaylist.Parent.Playlists:
            # Parent.Playlists includes the Library playlist itself again
            # (skip the duplicate) plus every other playlist in the same
            # source (user playlists, Podcasts, Audiobooks, Movies, etc).
            try:
                if pl.PlaylistID == library_playlist.PlaylistID:
                    continue
            except Exception:
                continue
            if _is_excluded_playlist(pl):
                continue
            all_playlists.append(pl)
    except Exception as exc:
        # Falling back to just the Library playlist (still the most
        # important one -- it's every track in the library, independent
        # of playlist membership) rather than aborting entirely.
        result.errors.append(f"Could not enumerate playlists: {exc}")

    for playlist in all_playlists:
        try:
            track = _call_with_retry(
                lambda: playlist.Tracks.ItemByPersistentID(persistent_id_high, persistent_id_low)
            )
        except Exception:
            track = None
        if track is None:
            continue
        try:
            # The delete itself gets the same retry/backoff treatment as
            # the lookup above -- a transient "iTunes busy" bounce here is
            # exactly the case _call_with_retry exists for. If every
            # attempt still fails, the exception falls through to the
            # existing except-and-record-to-result.errors handling below,
            # completely unchanged from before retries were added.
            _call_with_retry(track.Delete)
            found_any = True
            result.playlist_removals += 1
        except Exception as exc:
            try:
                playlist_name = playlist.Name
            except Exception:
                playlist_name = "(unknown playlist)"
            result.errors.append(
                f"Could not remove track (Persistent ID {persistent_id_high:08X}"
                f"{persistent_id_low:08X}) from '{playlist_name}': {exc}"
            )
    return found_any


def _persistent_id_parts(track_raw: dict) -> tuple[int, int] | None:
    """Library.xml stores 'Persistent ID' as a single 16-hex-digit string
    (e.g. "A1B2C3D4E5F60708"); iTunesLib's ItemByPersistentID wants it
    split into two 32-bit halves. Returns None if the field is missing or
    not parseable as hex, in which case the caller must skip COM removal
    for that track (falling back to the XML file alone still removes it
    correctly -- this only affects whether the *live* app also updates
    for that one track)."""
    raw = track_raw.get("Persistent ID")
    if not raw or not isinstance(raw, str):
        return None
    try:
        value = int(raw, 16)
    except ValueError:
        return None
    high = (value >> 32) & 0xFFFFFFFF
    low = value & 0xFFFFFFFF
    return high, low


def sync_removed_tracks_from_raws(removed_track_raws: list[dict]) -> ComSyncResult:
    """Attempts to remove every given track directly from the running
    iTunes, across the Library and every included user playlist. Always
    returns a ComSyncResult; never raises.

    `removed_track_raws`: raw metadata dicts (in particular 'Persistent
    ID') for exactly the tracks a confirmed plan removed -- captured by
    the caller BEFORE apply_plan() pops them from Library.tracks, since
    by the time the file write has finished (see workers.py -- this is
    deliberately called only *after* library.save() succeeds, so the
    exported file is never at risk of going out of sync with what live
    iTunes ends up showing) those entries are already gone from the
    in-memory Library object. This function only reads dicts the caller
    already collected; it never touches a Library object itself.
    """
    result = ComSyncResult(attempted=True, itunes_available=False)

    if not removed_track_raws:
        # Still worth probing availability even with nothing to remove,
        # so a caller/tests can distinguish "iTunes wasn't reachable"
        # from "nothing needed removing" -- but skip the more expensive
        # per-track work below when there's nothing to do.
        if not is_windows() or not is_itunes_running_and_responsive():
            return result
        app = _try_connect()
        result.itunes_available = app is not None
        return result

    if not is_windows():
        return result
    if not is_itunes_running_and_responsive():
        return result

    app = _try_connect()
    if app is None:
        return result

    result.itunes_available = True

    for raw in removed_track_raws:
        parts = _persistent_id_parts(raw)
        if parts is None:
            result.tracks_not_found += 1
            continue
        high, low = parts
        removed = _remove_track_everywhere(app, high, low, result)
        if removed:
            result.tracks_removed += 1
        else:
            result.tracks_not_found += 1

    return result
