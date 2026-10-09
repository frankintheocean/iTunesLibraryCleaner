"""
Minimal error logging, ported from WhiteBoard so the two apps start up
the same way: every otherwise-unhandled exception reaching the Qt event
loop is recorded here -- appended to a small on-disk error.log in the
app's data directory, and kept in an in-memory ring buffer. This is
diagnostic only -- it never changes control flow, never raises itself,
and a failure to log (e.g. disk full) is swallowed rather than surfacing
a second error on top of whatever was already being handled.

Deliberately not using the stdlib `logging` module: this app has exactly
one place errors need to be recorded, and a few lines of direct file I/O
plus a bounded list avoids pulling in logging's handler/formatter/
logger-hierarchy machinery (and its own process-wide global state) for a
need this small.
"""
from __future__ import annotations

import os
import time
import traceback
from typing import List, Optional

# Cap the in-memory buffer and the on-disk file independently: the buffer
# only needs to hold enough to show something useful at a glance, while
# the file is allowed to hold more history since it's just appended text.
MAX_MEMORY_ENTRIES = 50
MAX_LOG_FILE_BYTES = 512 * 1024  # 512KB -- trimmed from the front when exceeded

_entries: List[str] = []
_log_path: Optional[str] = None


def init(data_dir: str) -> None:
    """Point the logger at the app's data directory. Called once from
    main.py right after the app data dir is known -- before this is
    called, log_error() below still works (appends to the in-memory
    buffer), it just can't write to disk yet, so an exception raised
    before init() can run is never lost."""
    global _log_path
    try:
        os.makedirs(data_dir, exist_ok=True)
        _log_path = os.path.join(data_dir, "error.log")
    except OSError:
        # No writable data dir (unusual, but not fatal): logging simply
        # stays in-memory-only for this session rather than raising here,
        # since this runs during startup before any UI exists to show an
        # error about the error logger itself.
        _log_path = None


def log_error(context: str, exc: BaseException = None) -> None:
    """Record one error. context: a short human-readable description of
    what was happening (e.g. "Startup", "Load library") -- not a full
    sentence, just enough to tell entries apart. exc: the exception, if
    any (also accepts None for a bare message). Never raises: a failure
    here must never mask or replace whatever error triggered the call in
    the first place."""
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        if exc is not None:
            detail = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ).strip()
        else:
            detail = ""
        entry = f"[{timestamp}] {context}" + (f"\n{detail}" if detail else "")
        _entries.append(entry)
        if len(_entries) > MAX_MEMORY_ENTRIES:
            del _entries[: len(_entries) - MAX_MEMORY_ENTRIES]
        _append_to_file(entry)
    except Exception:
        # Logging must never itself crash the app or the caller's own
        # except block -- silently drop if anything above went wrong.
        pass


def _append_to_file(entry: str) -> None:
    """Appends `entry` to the on-disk log, keeping the file within
    MAX_LOG_FILE_BYTES.

    Fast path: append the new bytes directly (O(entry size), not O(file
    size)) whenever that alone can't push the file over the cap -- the
    overwhelmingly common case, since one entry is a handful of lines and
    the cap is 512KB. Only on the rare occasion a single append would
    cross the cap do we pay for a read-trim-rewrite, and even then we only
    read back enough trailing bytes to satisfy the cap plus one entry's
    worth of slack, not the whole file.

    All trimming/measuring is done in encoded bytes throughout (never
    Python character count), so the cap is honored regardless of
    content -- a str slice can silently leave the file over the byte cap
    when it contains multi-byte UTF-8 characters (e.g. non-English
    artist/track names in a traceback), since one character can be up to
    4 bytes."""
    if _log_path is None:
        return
    entry_bytes = entry.encode("utf-8", errors="ignore")
    separator = b"\n\n"
    try:
        current_size = os.path.getsize(_log_path) if os.path.exists(_log_path) else 0
    except OSError:
        current_size = 0

    to_append = (separator if current_size else b"") + entry_bytes
    if current_size + len(to_append) <= MAX_LOG_FILE_BYTES:
        try:
            with open(_log_path, "ab") as f:
                f.write(to_append)
        except OSError:
            pass
        return

    # Appending would exceed the cap: fall back to reading the file back
    # (still bounded -- at most MAX_LOG_FILE_BYTES on disk already), then
    # trim from the front by bytes and rewrite atomically via a temp file
    # + os.replace so a crash/power-loss mid-write can never leave a
    # torn/partial log file behind.
    try:
        existing_bytes = b""
        if os.path.exists(_log_path):
            try:
                with open(_log_path, "rb") as f:
                    existing_bytes = f.read()
            except OSError:
                existing_bytes = b""
        combined_bytes = existing_bytes + to_append
        if len(combined_bytes) > MAX_LOG_FILE_BYTES:
            trimmed = combined_bytes[-MAX_LOG_FILE_BYTES:]
            # A raw byte-offset slice can land inside a multi-byte UTF-8
            # sequence, leaving an invalid leading byte on disk (e.g. a
            # continuation byte with no lead byte before it) that a
            # strict decoder -- or a person opening this file in an
            # editor that assumes valid UTF-8 -- would choke on. Drop up
            # to 3 leading bytes (the longest a UTF-8 sequence can be)
            # until what remains starts cleanly, rather than leaving a
            # dangling partial character at the front.
            for _ in range(3):
                try:
                    trimmed.decode("utf-8")
                    break
                except UnicodeDecodeError:
                    trimmed = trimmed[1:]
            combined_bytes = trimmed
        tmp_path = _log_path + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(combined_bytes)
        os.replace(tmp_path, _log_path)
    except OSError:
        pass


def recent_entries() -> List[str]:
    """Most-recent-first list of in-memory entries."""
    return list(reversed(_entries))


def entry_count() -> int:
    return len(_entries)


def clear() -> None:
    """Clear the in-memory buffer and truncate the on-disk file.
    Best-effort like everything else here -- if the file can't be
    truncated, the in-memory buffer is still cleared so the visible
    state empties either way."""
    _entries.clear()
    if _log_path is not None:
        try:
            with open(_log_path, "w", encoding="utf-8"):
                pass
        except OSError:
            pass
