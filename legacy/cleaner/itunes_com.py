"""
Thin wrapper around the iTunes COM interface (win32com). Ported from
GenreCleanup.hta's DoTrackDelete / DoGenreWrite / persistent-ID handling.

Key fact this file exists to get right: IITTrack has NO .PersistentID
property. iTunes only exposes it via IiTunes.ITObjectPersistentIDHigh(obj)
and IiTunes.ITObjectPersistentIDLow(obj) on the *application* object
(added in iTunes 7.7's COM interface after IITObject itself was frozen),
and IITTrackCollection.ItemByPersistentID takes two signed 32-bit Longs
(highID, lowID) - not one combined value. This was the root cause of the
original HTA's "NoPersistentID" delete failures.
"""
import logging
import time
from contextlib import contextmanager

try:
    import win32com.client
    import pywintypes
    import pythoncom
except ImportError:  # pragma: no cover - only importable on Windows
    win32com = None
    pywintypes = None
    pythoncom = None

log = logging.getLogger(__name__)


class ITunesError(Exception):
    pass


def describe_exception(e) -> str:
    """Returns a verbose, debug-log-only description of a COM (or any
    other) exception raised while talking to iTunes.

    ``pywintypes.com_error`` carries far more than ``str(e)`` shows in
    the user-facing changelog/UI: an HRESULT, a short COM-source
    message, an optional ``excepinfo`` tuple (source app, description,
    help file, help ID, wcode, scode - populated when iTunes itself
    raised the error rather than the COM plumbing), and an ``argerror``
    index when a specific call argument was rejected. None of that is
    fit for the user-facing summary (it's noisy and Windows/iTunes-
    version-specific), but it's exactly what's useful when triaging a
    user-reported "genre write failed" report against the debug log.
    Best-effort: never raises, and falls back to repr(e) for anything
    that isn't a com_error.
    """
    if pywintypes is not None and isinstance(e, pywintypes.com_error):
        try:
            hresult, message, excepinfo, argerror = e.args
        except (ValueError, AttributeError):
            return repr(e)
        parts = [f"hresult=0x{hresult & 0xFFFFFFFF:08X}", f"message={message!r}"]
        if excepinfo:
            try:
                wcode, source, description, helpfile, helpcontext, scode = excepinfo
                parts.append(
                    f"excepinfo=(wcode={wcode}, source={source!r}, "
                    f"description={description!r}, scode=0x{(scode or 0) & 0xFFFFFFFF:08X})"
                )
            except (ValueError, TypeError):
                parts.append(f"excepinfo={excepinfo!r}")
        if argerror is not None:
            parts.append(f"argerror={argerror}")
        return "COM error: " + ", ".join(parts)
    return repr(e)


@contextmanager
def com_apartment():
    """Own the COM apartment for the current thread from entry to exit."""
    if pythoncom is None:
        yield
        return
    pythoncom.CoInitialize()
    try:
        yield
    finally:
        pythoncom.CoUninitialize()


def connect():
    """Return an iTunes COM application in the caller's COM apartment.

    Callers that run on a worker thread should wrap their work in
    ``with com_apartment():`` so initialization and uninitialization are
    structurally paired. Reconnects then reuse the same apartment.
    """
    if win32com is None:
        raise ITunesError("pywin32 is required to run this on Windows.")
    return win32com.client.Dispatch("iTunes.Application")


def get_persistent_id_str(app, track) -> str:
    """Returns a track's persistent ID as a 16-char hex string
    (8 hi + 8 lo), or "" if unavailable."""
    try:
        hi = app.ITObjectPersistentIDHigh(track)
        lo = app.ITObjectPersistentIDLow(track)
    except Exception:
        return ""
    return f"{hi & 0xFFFFFFFF:08X}{lo & 0xFFFFFFFF:08X}"


def split_persistent_id_str(pid_str: str):
    """Splits a 16-char hex string back into the two signed 32-bit
    ints ItemByPersistentID(highID, lowID) expects."""
    if len(pid_str) != 16:
        return 0, 0
    hi = int(pid_str[:8], 16)
    lo = int(pid_str[8:], 16)
    # Wrap unsigned 32-bit hex into signed range, same as VBScript's
    # &H literal -> Long coercion.
    if hi >= 0x80000000:
        hi -= 0x100000000
    if lo >= 0x80000000:
        lo -= 0x100000000
    return hi, lo


def item_by_persistent_id(tracks_collection, pid_str: str):
    hi, lo = split_persistent_id_str(pid_str)
    try:
        return tracks_collection.ItemByPersistentID(hi, lo)
    except Exception:
        return None


def list_playlist_names(app):
    """Returns a sorted list of user-visible playlist names in the
    active iTunes source, for the library-scope picker. Best-effort:
    playlists that raise on .Name are skipped rather than failing the
    whole listing."""
    names = []
    try:
        playlists = app.LibraryPlaylist.Parent.Playlists
        count = playlists.Count
        for i in range(1, count + 1):
            try:
                pl = playlists.Item(i)
                name = getattr(pl, "Name", "")
                if name:
                    names.append(name)
            except Exception:
                continue
    except Exception:
        pass
    return sorted(set(names), key=str.lower)


def get_playlist_by_name(app, name: str):
    """Returns the named playlist object, or None if not found (or on
    any COM error)."""
    if not name:
        return None
    try:
        playlists = app.LibraryPlaylist.Parent.Playlists
        count = playlists.Count
        for i in range(1, count + 1):
            try:
                pl = playlists.Item(i)
                if getattr(pl, "Name", "") == name:
                    return pl
            except Exception:
                continue
    except Exception:
        pass
    return None


def enumerate_tracks(library_playlist):
    """Yields every track in the library playlist via COM enumeration
    (fast, avoids repeated indexed Item(n) calls which slow down on
    large libraries)."""
    tracks = library_playlist.Tracks
    count = tracks.Count
    for i in range(1, count + 1):
        try:
            yield tracks.Item(i)
        except Exception:
            continue


def safe_get(track, attr, default=""):
    try:
        val = getattr(track, attr)
        return val if val is not None else default
    except Exception:
        return default


def do_genre_write(track, new_genre: str) -> bool:
    """Writes a new genre value to a track. Returns True on success."""
    ok, _err = do_genre_write_diag(track, new_genre)
    return ok


def do_genre_write_diag(track, new_genre: str):
    """Same as do_genre_write, but also returns a diagnostic message on
    failure (e.g. a locked file or COM error) instead of discarding it,
    so callers can surface *why* a write failed rather than just a
    count. Returns (True, "") on success, (False, err_msg) otherwise."""
    try:
        track.Genre = new_genre
        return True, ""
    except Exception as e:
        log.debug("Genre write failure detail: %s", describe_exception(e))
        return False, f"Genre write failed: {e}"


def do_fields_write_diag(track, fields: dict):
    """Writes several track properties in one go (e.g. Album,
    AlbumArtist, DiscNumber, DiscCount, TrackNumber, TrackCount, Year,
    Compilation) - used by the album-merge feature so a track's whole
    set of album-identity fields updates atomically from the caller's
    point of view. Same success/diagnostic contract as
    do_genre_write_diag: returns (True, "") on success, or
    (False, err_msg) naming the first field that failed. Fields already
    matching the track are skipped (no-op write), same spirit as the
    genre path's old_genre != new_genre check elsewhere."""
    for attr, value in fields.items():
        try:
            current = getattr(track, attr, None)
            if current == value:
                continue
            setattr(track, attr, value)
        except Exception as e:
            log.debug("Field write failure detail (%s): %s", attr, describe_exception(e))
            return False, f"{attr} write failed: {e}"
    return True, ""


def do_fields_write_with_fallback(app_factory, persistent_id: str, fields: dict,
                                   retries: int = 1, settle_seconds: float = 0.6,
                                   app=None, track=None):
    """Same reused-session-first, reconnect-on-failure fallback as
    do_genre_write_with_fallback, but for do_fields_write_diag's
    multi-field write. Returns (True, "") on success, (False, err_msg)
    otherwise."""
    last_err = "Unknown error"
    current_app = app
    current_track = track
    for attempt in range(retries + 1):
        if current_track is None:
            if current_app is None:
                if not persistent_id:
                    return False, "No usable PersistentID"
                try:
                    current_app = app_factory()
                except Exception as e:
                    log.debug("Fields-write reconnect failure detail: %s", describe_exception(e))
                    last_err = f"Reconnect failed: {e}"
                    continue
            try:
                lib = current_app.LibraryPlaylist
                current_track = item_by_persistent_id(lib.Tracks, persistent_id)
            except Exception as e:
                log.debug("Fields-write reconnect-refetch failure detail: %s", describe_exception(e))
                last_err = f"Reconnect-Refetch failed: {e}"
                current_app = None
                continue
            if current_track is None:
                last_err = "Reconnect-Refetch: track not found"
                current_app = None
                continue
        ok, err = do_fields_write_diag(current_track, fields)
        if ok:
            return True, ""
        last_err = err
        current_app = None
        current_track = None
        if attempt < retries:
            time.sleep(settle_seconds)
    return False, last_err


def do_genre_write_with_fallback(app_factory, persistent_id: str, new_genre: str,
                                  retries: int = 1, settle_seconds: float = 0.6,
                                  app=None, track=None):
    """Writes a new genre value, retrying against a freshly reconnected
    session on failure. Mirrors do_track_delete's reused-session-first,
    reconnect-on-failure fallback, since a flaky COM session can affect
    genre writes the same way it affects deletes.

    track: an already-resolved IITTrack to try first (avoids a redundant
    lookup on the common case where the caller already has it from
    enumeration). app/persistent_id are used to re-resolve the track
    against a fresh session on retry.

    Returns (True, "") on success, (False, err_msg) otherwise.
    """
    last_err = "Unknown error"
    current_app = app
    current_track = track
    for attempt in range(retries + 1):
        if current_track is None:
            if current_app is None:
                if not persistent_id:
                    return False, "No usable PersistentID"
                try:
                    current_app = app_factory()
                except Exception as e:
                    log.debug("Genre-write reconnect failure detail: %s", describe_exception(e))
                    last_err = f"Reconnect failed: {e}"
                    continue
            try:
                lib = current_app.LibraryPlaylist
                current_track = item_by_persistent_id(lib.Tracks, persistent_id)
            except Exception as e:
                log.debug("Genre-write reconnect-refetch failure detail: %s", describe_exception(e))
                last_err = f"Reconnect-Refetch failed: {e}"
                current_app = None
                continue
            if current_track is None:
                last_err = "Reconnect-Refetch: track not found"
                current_app = None
                continue
        ok, err = do_genre_write_diag(current_track, new_genre)
        if ok:
            return True, ""
        last_err = err
        # As with delete, drop the session/track that just failed and
        # force a fresh app_factory() session + re-resolved track on retry.
        current_app = None
        current_track = None
        if attempt < retries:
            time.sleep(settle_seconds)
    return False, last_err


def do_track_delete(app_factory, persistent_id: str, retries: int = 1,
                     settle_seconds: float = 0.6, app=None):
    """Deletes a track by persistent ID. Returns (ok, err_msg).

    app_factory is a zero-arg callable returning a fresh iTunes.Application
    (normally itunes_com.connect), used only as a fallback if the reused
    session (app) is missing or a delete attempt fails on it - mirrors the
    HTA's original reconnect-on-failure behavior without paying the cost
    of a brand-new COM session on every single delete.

    app: an existing iTunes.Application to reuse first. When omitted or
    when a delete attempt against it fails, this falls back to
    app_factory() to get a fresh session, exactly as before.
    """
    if not persistent_id:
        return False, "No usable PersistentID"

    last_err = "Unknown error"
    current_app = app
    for attempt in range(retries + 1):
        if current_app is None:
            try:
                current_app = app_factory()
            except Exception as e:
                log.debug("Delete reconnect failure detail: %s", describe_exception(e))
                last_err = f"Reconnect failed: {e}"
                continue
        try:
            lib = current_app.LibraryPlaylist
        except Exception as e:
            log.debug("Delete reconnect-library failure detail: %s", describe_exception(e))
            last_err = f"Reconnect-Library failed: {e}"
            current_app = None
            continue
        try:
            target_track = item_by_persistent_id(lib.Tracks, persistent_id)
        except Exception as e:
            log.debug("Delete reconnect-refetch failure detail: %s", describe_exception(e))
            last_err = f"Reconnect-Refetch failed: {e}"
            current_app = None
            continue
        if target_track is None:
            last_err = "Reconnect-Refetch: track not found"
            current_app = None
            continue
        try:
            target_track.Delete()
            return True, ""
        except Exception as e:
            log.debug("Delete failure detail: %s", describe_exception(e))
            last_err = f"Delete failed: {e}"
            # The session that just failed a Delete() may be in a bad
            # state (mirrors the original per-call reconnect rationale) -
            # drop it and force a fresh app_factory() session on retry.
            current_app = None
            if attempt < retries:
                time.sleep(settle_seconds)
            continue
    return False, last_err
