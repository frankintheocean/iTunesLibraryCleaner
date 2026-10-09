"""
Single-instance-per-library advisory lock.

Prevents two instances of this app (or two windows within one instance)
from opening and writing back to the *same* Library.xml file at the same
time, which could otherwise race and produce a torn/inconsistent write.
This is deliberately scoped per-file, not "only one instance of the app
allowed" -- opening two different libraries in two windows is fine and
unaffected.

Implementation: one small marker file per locked library, written next
to the app's own data directory (never inside the user's Music folder),
named by a hash of the resolved library path so it's stable across runs.
Locking itself uses the file's OS-level advisory lock (msvcrt on Windows,
fcntl elsewhere) so a crashed process automatically releases it -- no
stale-lock cleanup logic is needed, unlike a plain "does this file exist"
check, which a crash could leave behind forever.

Dependency-free: uses only the stdlib (msvcrt is part of the Python
standard library on Windows; fcntl is part of the standard library on
POSIX), matching every other part of this app that avoids adding new
third-party packages for something the stdlib already covers.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Optional


class LibraryAlreadyOpenError(Exception):
    """Raised when another process already holds the lock for this
    Library.xml. Carries no extra data beyond the message -- the caller
    (main_window) is expected to show it via with_recovery_guidance."""


class LibraryLock:
    """Holds an OS-level advisory lock on one library file for the
    lifetime of this object. Call acquire() before treating a library as
    "this instance's to write to"; call release() (or just let the
    object be garbage-collected/close()'d) when done with it or before
    locking a different library."""

    def __init__(self, lock_dir: Path, library_path: Path):
        lock_dir.mkdir(parents=True, exist_ok=True)
        # Resolve so the same library opened via two different-looking
        # paths (e.g. a relative path vs. its absolute form, or two
        # different drive-letter casings) still maps to the same lock
        # file -- otherwise the two instances would each think they hold
        # a lock on a "different" file and neither would see the other.
        try:
            resolved = str(library_path.resolve()).lower()
        except OSError:
            resolved = str(library_path).lower()
        digest = hashlib.sha256(resolved.encode("utf-8", "replace")).hexdigest()[:16]
        self._lock_path = lock_dir / f"{digest}.lock"
        self._fh = None  # type: ignore[assignment]

    def acquire(self) -> None:
        """Attempts to take the lock. Raises LibraryAlreadyOpenError if
        another process already holds it. Safe to call more than once on
        the same LibraryLock instance (e.g. re-opening the same library)
        -- re-acquiring a lock this same object already holds is a no-op."""
        if self._fh is not None:
            return  # already held by this instance

        fh = open(self._lock_path, "a+")
        try:
            if sys.platform == "win32":
                import msvcrt

                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    fh.close()
                    raise LibraryAlreadyOpenError(
                        "This Library.xml is already open in another window "
                        "or another copy of this app. Close it there first, "
                        "or finish working in that window before opening the "
                        "same file here."
                    ) from exc
            else:
                import fcntl

                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    fh.close()
                    raise LibraryAlreadyOpenError(
                        "This Library.xml is already open in another window "
                        "or another copy of this app. Close it there first, "
                        "or finish working in that window before opening the "
                        "same file here."
                    ) from exc
        except ImportError:
            # Neither msvcrt nor fcntl available (unexpected platform) --
            # fail open rather than block the app from ever loading a
            # library; the lock is a best-effort safety net, not a
            # feature the app hard-depends on to function.
            pass
        self._fh = fh

    def release(self) -> None:
        """Releases the lock, if held. Safe to call multiple times or
        when the lock was never acquired."""
        if self._fh is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                try:
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                try:
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        except ImportError:
            pass
        finally:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None

    def __del__(self) -> None:  # best-effort cleanup if release() was missed
        try:
            self.release()
        except Exception:
            pass
