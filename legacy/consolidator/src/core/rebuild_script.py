"""
Swaps a cleaned Library.xml into the user's real iTunes data folder and
forces iTunes to rebuild its binary "iTunes Library.itl" from it, entirely
in-app.

Why this exists: classic Windows iTunes does not read Library.xml as its
working database -- that file is normally just an *export*. The actual
library iTunes opens on launch is "iTunes Library.itl", a binary file.
Replacing/editing the .xml alone does nothing until iTunes is pointed at
a folder with no .itl present (via the Shift-launch "choose library"
prompt), at which point it rebuilds the .itl from the .xml.

(Removed in 1.6.7-pre: this module used to also generate a standalone
.bat script the user could run by hand as an alternative to the in-app
rebuild below. The in-app rebuild does the same swap-and-relaunch with
stronger checks -- e.g. verified copy sizes, confirmed process exit,
stray-.xml cleanup -- that the .bat version never had, so maintaining
both risked the two quietly drifting apart. The .bat path is gone,
and rebuild_library_in_app() is now the only way this app performs
the swap.)
"""

from __future__ import annotations

import datetime
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


def default_itunes_dir() -> Path:
    """Best-guess default iTunes data folder (Windows layout)."""
    return Path.home() / "Music" / "iTunes"


# Backup filename timestamp format: day/month/year_24hr-time, e.g.
# "16-08-2026_143005" for 2026-08-16 14:30:05. Changed from the old
# "%Y%m%d_%H%M%S" (sortable-by-string) format to this day-first one on
# user request -- day-first stamps do NOT sort correctly as plain
# strings (e.g. "16-08-2026" < "05-09-2026" alphabetically even though
# September is later), so anything that needs "the newest backup" must
# parse the stamp with _parse_backup_stamp() below and compare the
# resulting datetimes, never compare the raw stamp strings themselves.
_BACKUP_STAMP_FORMAT = "%d-%m-%Y_%H%M%S"


def _parse_backup_stamp(stamp: str) -> "datetime.datetime | None":
    """Parses a backup filename stamp (see _BACKUP_STAMP_FORMAT) back into
    a datetime for chronological comparison. Returns None for anything
    that doesn't match -- e.g. a backup left over from a build that used
    the old "%Y%m%d_%H%M%S" format -- so callers can skip/ignore
    unparseable stamps instead of crashing on them."""
    try:
        return datetime.datetime.strptime(stamp, _BACKUP_STAMP_FORMAT)
    except ValueError:
        return None


def _prune_old_backups(itunes_dir: Path, glob_pattern: str, prefix: str, keep_path: Path) -> None:
    """Deletes every backup matching glob_pattern in itunes_dir except
    keep_path, so only the single most recent backup of that kind is ever
    left on disk (user request: "only store most recent backup, delete
    older backups to save storage space"). keep_path is always preserved
    even if, for some reason, it doesn't turn out to be the newest by
    parsed timestamp -- this only ever prunes *other* files, it never
    second-guesses which file the caller just backed up to.

    Best-effort: a file that can't be deleted (permissions, held open by
    another process, etc.) is left in place rather than raising, since a
    failed prune is not worth turning a successful backup into a reported
    failure over -- matches this module's existing "never raise for
    expected failure modes" convention.
    """
    try:
        candidates = itunes_dir.glob(glob_pattern)
    except OSError:
        return
    for path in candidates:
        if path == keep_path:
            continue
        try:
            path.unlink()
        except OSError:
            pass


# Relative sub-paths (under a drive root or a drive's Users\<name> folder)
# where an iTunes data folder is commonly found, newest/most-common layout
# first. Kept separate from default_itunes_dir() (which only ever checks
# the current user's home) so autodetect_itunes_dir() below can walk every
# other drive letter too -- for anyone whose library lives on a secondary
# internal drive, an external drive, or a portable/removable one, not just
# wherever the OS user profile happens to be.
_ITUNES_DIR_SUFFIXES = (
    ("Music", "iTunes"),
    ("iTunes",),
)

# Only the drive letters worth scanning -- C: through Z:, skipping A:/B:
# (legacy floppy-drive letters; probing them can trigger a slow "insert
# disk" prompt on some Windows configurations, so they're deliberately
# excluded rather than scanned and discarded).
_SCANNABLE_DRIVE_LETTERS = tuple("CDEFGHIJKLMNOPQRSTUVWXYZ")


def autodetect_itunes_dir_candidates() -> list[Path]:
    """Scans common drive letters for a folder that looks like a real
    iTunes data folder (contains iTunes Library.itl), so first-launch
    setup doesn't have to make someone browse blind if they don't already
    know where their library lives. Returns every match found, most-likely
    location first; the caller decides what to do if it's empty (fall back
    to default_itunes_dir() and let the user browse manually) or if there's
    more than one (e.g. offer a picker, or just take the first).

    Only ever reads the filesystem (Path.exists()/is_dir()) -- never
    writes, never touches the registry, never launches anything. A drive
    that isn't present, isn't ready (e.g. a mounted DVD tray with no disc),
    or errors for any other reason is silently skipped rather than raising,
    since "some drives aren't scannable" is the normal case, not a failure
    worth interrupting startup for.
    """
    if not is_windows():
        return []

    found: list[Path] = []
    seen: set[Path] = set()

    def _consider(path: Path) -> None:
        try:
            if not path.is_dir():
                return
            if not (path / "iTunes Library.itl").exists():
                return
            resolved = path.resolve()
        except OSError:
            return
        if resolved in seen:
            return
        seen.add(resolved)
        found.append(path)

    # Current user's home directory first (covers the common case fastest,
    # and matches default_itunes_dir()'s own layout) before falling back to
    # a broader per-drive sweep.
    home = Path.home()
    for suffix in _ITUNES_DIR_SUFFIXES:
        _consider(home.joinpath(*suffix))

    for letter in _SCANNABLE_DRIVE_LETTERS:
        drive_root = Path(f"{letter}:\\")
        try:
            if not drive_root.exists():
                continue
        except OSError:
            # Optical/removable drives with no media report errors here
            # rather than simply False -- treat the same as "not present".
            continue
        # Drive root itself (external drives with the iTunes folder copied
        # straight to the top level), then the usual Users\<name>\Music
        # layout for every profile on that drive.
        for suffix in _ITUNES_DIR_SUFFIXES:
            _consider(drive_root.joinpath(*suffix))
        users_dir = drive_root / "Users"
        try:
            profile_dirs = list(users_dir.iterdir()) if users_dir.is_dir() else []
        except OSError:
            profile_dirs = []
        for profile_dir in profile_dirs:
            for suffix in _ITUNES_DIR_SUFFIXES:
                _consider(profile_dir.joinpath(*suffix))

    return found


def autodetect_itunes_dir() -> Path | None:
    """Single best-guess iTunes data folder found by scanning common drive
    letters (see autodetect_itunes_dir_candidates), or None if nothing was
    found anywhere. Never overrides a value the user has already set
    manually -- callers should only use this to pre-fill/suggest a folder
    the first time one hasn't been confirmed yet."""
    candidates = autodetect_itunes_dir_candidates()
    return candidates[0] if candidates else None


# ------------------------------------------------------- In-app rebuild

# Coarse step vocabulary for the in-app rebuild sequence, emitted via the
# optional `on_step` callback below so the UI can show a step tracker
# (e.g. "Step 2/4: Backing up") instead of a single indeterminate
# spinner with no indication of which part of the sequence is running.
STEP_QUITTING = "Quitting iTunes"
STEP_BACKING_UP = "Backing up"
STEP_COPYING = "Copying"
STEP_RELAUNCHING = "Relaunching"
REBUILD_STEPS = (STEP_QUITTING, STEP_BACKING_UP, STEP_COPYING, STEP_RELAUNCHING)

_ITUNES_EXE_CANDIDATES = (
    r"C:\Program Files (x86)\iTunes\iTunes.exe",
    r"C:\Program Files\iTunes\iTunes.exe",
)

_KILL_WAIT_SECONDS = 8.0
_KILL_POLL_INTERVAL_SECONDS = 0.25


@dataclass
class RebuildResult:
    """Outcome of one in-app rebuild attempt. Always returned, never
    raised for expected failure modes -- see rebuild_library_in_app()."""
    ok: bool
    message: str
    itl_backup_path: Path | None = None
    xml_backup_path: Path | None = None
    itunes_relaunched: bool = False
    warnings: list[str] = field(default_factory=list)
    # Any other *.xml files found sitting in the iTunes folder besides the
    # main "iTunes Library.xml" (e.g. a stray manual export, or a leftover
    # from a previous tool/version) get backed up alongside it -- never
    # deleted outright -- so they can't confuse iTunes's own "Choose
    # Library..." folder scan or a future re-import. Maps each original
    # path to where it was backed up. Empty in the common case where no
    # such extra files exist.
    extra_xml_backups: dict[Path, Path] = field(default_factory=dict)


@dataclass
class PreflightResult:
    """Outcome of preflight_check_rebuild() -- run before any part of the
    quit/backup/copy/relaunch sequence starts, so a problem that would
    otherwise only surface midway through (e.g. after iTunes has already
    been quit) is caught while it's still safe to simply not proceed.
    `ok` is True only if every check passed; `problems` lists every
    failed check's human-readable reason (not just the first), and
    `warnings` lists non-blocking concerns worth surfacing but not worth
    stopping for (e.g. iTunes not currently running -- fine, just means
    the "quit" step will be a no-op)."""
    ok: bool
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Rough safety margin for the free-space check: the rebuild only ever
# writes one new "iTunes Library.xml" (a copy of cleaned_xml_path) plus
# up to two small timestamped backups of files already in itunes_dir, so
# this doesn't need to account for the .itl at all -- but a flat
# multiplier (rather than exactly 1x the cleaned XML's size) leaves
# headroom for those backups and for the temp-file-then-rename copy step
# briefly holding two copies of the XML at once.
_PREFLIGHT_SPACE_MULTIPLIER = 3
_PREFLIGHT_MIN_FREE_BYTES = 50 * 1024 * 1024  # floor for tiny libraries


def preflight_check_rebuild(
    cleaned_xml_path: Path,
    itunes_dir: Path | None = None,
) -> PreflightResult:
    """Checks the things that would otherwise only be discovered partway
    through rebuild_library_in_app() -- disk space, write permissions on
    the destination folder, and whether iTunes is currently running --
    all up front, before anything is quit, moved, or deleted. Meant to be
    called immediately before starting the rebuild sequence (see
    ui/main_window._on_rebuild_library_in_app), not partway through it.

    Never raises -- every failure mode is reported in the returned
    PreflightResult so the caller can show it without a try/except of
    its own, matching rebuild_library_in_app()'s own convention.

    iTunes currently running is deliberately a *warning*, not a blocking
    problem: rebuild_library_in_app() already quits it itself as its
    first step, so failing preflight over something the rebuild handles
    on its own would just be a redundant extra prompt.
    """
    itunes_dir = itunes_dir or default_itunes_dir()
    problems: list[str] = []
    warnings: list[str] = []

    if not is_windows():
        problems.append("This only works on Windows (classic iTunes).")
        return PreflightResult(ok=False, problems=problems)

    if not cleaned_xml_path.exists():
        problems.append(f"Could not find the cleaned XML at:\n{cleaned_xml_path}")
        # Nothing else below depends on cleaned_xml_path existing except
        # the size check, so stop here rather than raise a confusing
        # second error about a file that was never going to be readable.
        return PreflightResult(ok=False, problems=problems, warnings=warnings)

    if not itunes_dir.exists():
        problems.append(
            f"Could not find an iTunes folder at:\n{itunes_dir}\n\n"
            "Double check this is the folder containing your real iTunes "
            "Library.itl (e.g. on an external drive, it won't be under "
            "your user profile's Music folder)."
        )
        return PreflightResult(ok=False, problems=problems, warnings=warnings)

    # Write permission: create-then-remove a throwaway marker file rather
    # than inspecting os.access()'s W_OK bit alone -- on Windows, W_OK
    # can report writable for folders the current user can't actually
    # write into (e.g. some redirected/OneDrive-backed folders enforce
    # this at open() time, not at the ACL level os.access() reads), so an
    # actual write is the only check that can't be fooled that way.
    probe_path = itunes_dir / ".ilc_preflight_write_test.tmp"
    try:
        probe_path.write_bytes(b"")
        probe_path.unlink()
    except OSError:
        problems.append(
            f"This app doesn't have permission to write to:\n{itunes_dir}\n\n"
            "Check the folder isn't read-only or set to \"Run as "
            "administrator\"-only access, then try again."
        )

    # Disk space: the destination volume needs room for the new XML (plus
    # backups and the brief temp-copy overlap -- see
    # _PREFLIGHT_SPACE_MULTIPLIER) before anything is quit or removed.
    try:
        needed_bytes = cleaned_xml_path.stat().st_size * _PREFLIGHT_SPACE_MULTIPLIER
        needed_bytes = max(needed_bytes, _PREFLIGHT_MIN_FREE_BYTES)
        free_bytes = shutil.disk_usage(itunes_dir).free
        if free_bytes < needed_bytes:
            problems.append(
                f"Not enough free space on the drive for {itunes_dir}: "
                f"about {free_bytes // (1024 * 1024)} MB free, "
                f"~{needed_bytes // (1024 * 1024)} MB needed.\n\n"
                "Free up some space on that drive and try again."
            )
    except OSError as exc:
        warnings.append(f"Could not check free disk space: {exc}")

    # iTunes running: not a blocker (rebuild_library_in_app quits it as
    # its own first step) but worth surfacing up front so the user isn't
    # surprised when it closes -- e.g. if they still have unsaved changes
    # open elsewhere in it.
    if _itunes_is_running():
        warnings.append(
            "iTunes is currently running -- it will be closed automatically "
            "as the first step of the rebuild."
        )

    return PreflightResult(ok=not problems, problems=problems, warnings=warnings)


@dataclass
class UndoResult:
    """Outcome of one "undo last rebuild" attempt. Always returned, never
    raised for expected failure modes -- mirrors RebuildResult above."""
    ok: bool
    message: str
    restored_itl: bool = False
    restored_xml: bool = False


def find_latest_rebuild_backup_pair(itunes_dir: Path) -> tuple[Path | None, Path | None, str | None]:
    """Finds the most recent .itl/.xml backup pair written by
    rebuild_library_in_app() (see the "_step(STEP_BACKING_UP)" block above
    -- files named "iTunes Library.itl.bak_<stamp>" / "iTunes Library.xml.
    bak_<stamp>") in the given iTunes folder, matched by their shared
    timestamp stamp so a partial/mismatched pair (e.g. only the .itl backup
    exists because the .xml didn't need backing up that run) is still
    handled -- either half may be None if that half wasn't found for the
    latest stamp.

    Returns (itl_backup_path_or_None, xml_backup_path_or_None,
    stamp_or_None). stamp is None only when no backup of either kind exists
    at all. Never raises -- an unreadable folder is treated the same as
    "no backups found"."""
    try:
        itl_backups = list(itunes_dir.glob("iTunes Library.itl.bak_*"))
        xml_backups = list(itunes_dir.glob("iTunes Library.xml.bak_*"))
    except OSError:
        return None, None, None

    def _stamp_of(p: Path, prefix: str) -> str:
        return p.name[len(prefix):]

    # Bug fix: the day/month/year backup stamp format (_BACKUP_STAMP_FORMAT)
    # does not sort correctly as a plain string (e.g. "16-08-2026" is
    # lexicographically before "05-09-2026" even though September is
    # later), so picking the "latest" file can no longer be a plain
    # sorted(...)[-1]/">=" string comparison -- each stamp is parsed back
    # into a real datetime and compared chronologically instead. A stamp
    # that fails to parse (e.g. left over from an older build that used
    # the previous "%Y%m%d_%H%M%S" format) is skipped rather than crashing
    # this lookup or being silently treated as "oldest".
    def _latest_by_parsed_stamp(paths: list[Path], prefix: str) -> tuple[Path | None, str | None]:
        best_path: Path | None = None
        best_stamp: str | None = None
        best_when: "datetime.datetime | None" = None
        for p in paths:
            stamp = _stamp_of(p, prefix)
            when = _parse_backup_stamp(stamp)
            if when is None:
                continue
            if best_when is None or when > best_when:
                best_when = when
                best_stamp = stamp
                best_path = p
        return best_path, best_stamp

    latest_itl, latest_itl_stamp = _latest_by_parsed_stamp(itl_backups, "iTunes Library.itl.bak_")
    latest_xml, latest_xml_stamp = _latest_by_parsed_stamp(xml_backups, "iTunes Library.xml.bak_")

    if latest_itl_stamp is None and latest_xml_stamp is None:
        return None, None, None

    # The two backups are written moments apart within the same rebuild
    # (see rebuild_library_in_app's single `stamp` value), so under normal
    # operation their stamps always match. If they don't -- e.g. only one
    # half was ever backed up for the most recent rebuild -- prefer
    # whichever stamp is chronologically newest (parsed via
    # _parse_backup_stamp, not compared as strings -- see above), and only
    # pair up the other file if it shares that exact stamp string;
    # otherwise leave it None rather than silently mixing backups from two
    # different rebuilds.
    itl_when = _parse_backup_stamp(latest_itl_stamp) if latest_itl_stamp else None
    xml_when = _parse_backup_stamp(latest_xml_stamp) if latest_xml_stamp else None
    if itl_when is not None and (xml_when is None or itl_when >= xml_when):
        newest_stamp = latest_itl_stamp
    else:
        newest_stamp = latest_xml_stamp

    itl_match = itunes_dir / f"iTunes Library.itl.bak_{newest_stamp}"
    xml_match = itunes_dir / f"iTunes Library.xml.bak_{newest_stamp}"
    return (
        itl_match if itl_match.exists() else None,
        xml_match if xml_match.exists() else None,
        newest_stamp,
    )


def undo_last_rebuild(
    itunes_dir: Path | None = None,
    on_step: Callable[[str], None] | None = None,
) -> UndoResult:
    """One-click "undo last rebuild": restores the most recent iTunes
    Library.itl/.xml backup pair (see find_latest_rebuild_backup_pair)
    over the current, just-rebuilt files, so the user doesn't have to
    manually find and rename the timestamped .bak_<stamp> files
    themselves. Quits iTunes first (same reasoning as rebuild_library_in_
    app: it must not be holding the .itl file open while it's replaced),
    then copies each found backup back to its original filename and
    relaunches iTunes so it picks the restored library straight up,
    without needing another "Choose Library..." prompt -- restoring the
    same iTunes Library.itl it already knew about is not the same
    situation rebuild_library_in_app() handles (that removes the .itl
    entirely to force the picker); this restores it in place.

    Never raises; every failure mode is reported in the returned
    UndoResult so the caller can show it without a try/except of its own.
    """
    itunes_dir = itunes_dir or default_itunes_dir()

    def _step(name: str) -> None:
        if on_step is not None:
            on_step(name)

    if not is_windows():
        return UndoResult(ok=False, message="This only works on Windows (classic iTunes).")

    if not itunes_dir.exists():
        return UndoResult(
            ok=False,
            message=f"Could not find an iTunes folder at:\n{itunes_dir}",
        )

    itl_backup, xml_backup, stamp = find_latest_rebuild_backup_pair(itunes_dir)
    if itl_backup is None and xml_backup is None:
        return UndoResult(
            ok=False,
            message=(
                "No rebuild backup was found in:\n"
                f"{itunes_dir}\n\n"
                "\"Undo last rebuild\" only works after \"Rebuild library "
                "now...\" has run at least once in this folder -- it "
                "restores the iTunes Library.itl/.xml backup that step "
                "made automatically."
            ),
        )

    _step(STEP_QUITTING)
    if not _quit_itunes():
        return UndoResult(
            ok=False,
            message=(
                "iTunes is still running and didn't close within the wait "
                "time, so nothing was restored -- undoing while it's still "
                "open risks it overwriting the restored files on its own "
                "exit. Close iTunes completely and try again."
            ),
        )

    itl_path = itunes_dir / "iTunes Library.itl"
    xml_path = itunes_dir / "iTunes Library.xml"
    restored_itl = False
    restored_xml = False

    _step(STEP_BACKING_UP)
    try:
        if itl_backup is not None:
            shutil.copy2(itl_backup, itl_path)
            restored_itl = True
    except OSError as exc:
        return UndoResult(
            ok=False,
            message=f"Could not restore iTunes Library.itl from its backup: {exc}",
        )

    try:
        if xml_backup is not None:
            shutil.copy2(xml_backup, xml_path)
            restored_xml = True
    except OSError as exc:
        return UndoResult(
            ok=False,
            message=(
                f"Restored iTunes Library.itl but could not restore iTunes "
                f"Library.xml from its backup: {exc}\n\nYour .itl backup "
                f"(dated {stamp}) was already restored -- only the .xml "
                f"half of this undo failed."
            ),
            restored_itl=restored_itl,
        )

    _step(STEP_RELAUNCHING)
    itunes_exe = find_itunes_exe()
    relaunched = False
    if itunes_exe is not None:
        try:
            subprocess.Popen([str(itunes_exe)])
            relaunched = True
        except OSError:
            pass

    restored_names = []
    if restored_itl:
        restored_names.append("iTunes Library.itl")
    if restored_xml:
        restored_names.append("iTunes Library.xml")
    message = (
        f"Restored {' and '.join(restored_names)} from the backup made "
        f"{stamp} in:\n{itunes_dir}"
    )
    if relaunched:
        message += "\n\niTunes has been reopened with the restored library."
    else:
        message += "\n\niTunes could not be relaunched automatically -- open it yourself."

    return UndoResult(ok=True, message=message, restored_itl=restored_itl, restored_xml=restored_xml)


def find_itunes_exe() -> Path | None:
    for candidate in _ITUNES_EXE_CANDIDATES:
        p = Path(candidate)
        if p.exists():
            return p
    return None


def _itunes_is_running() -> bool:
    """True if iTunes.exe currently has a running process, checked via
    tasklist rather than assumed from taskkill's exit code (taskkill
    reports success once termination is *requested*, not once the
    process has actually released its file handles)."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq iTunes.exe"],
            capture_output=True, text=True, check=False,
        )
    except Exception:
        return False
    return "iTunes.exe" in result.stdout


def _quit_itunes() -> bool:
    """Force-quits iTunes.exe if running and waits until tasklist
    confirms it's actually gone (up to _KILL_WAIT_SECONDS) -- not just
    that taskkill was issued. Returns True once the process is confirmed
    gone (or was never running), False if it's still running after the
    wait. Never raises -- best-effort, mirrors the same step in the
    generated .bat, but with an actual exit check added because a fixed
    sleep let the relaunch race ahead of iTunes actually releasing its
    Library.itl handle (and, on some versions, recreating an empty .itl
    on its way down), which is what caused iTunes not to show the
    "Choose Library..." prompt on relaunch even though the file had
    already been deleted once."""
    if not is_windows():
        return True
    try:
        subprocess.run(
            ["taskkill", "/IM", "iTunes.exe", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    except Exception:
        pass
    deadline = time.monotonic() + _KILL_WAIT_SECONDS
    while time.monotonic() < deadline:
        if not _itunes_is_running():
            return True
        time.sleep(_KILL_POLL_INTERVAL_SECONDS)
    return not _itunes_is_running()


def is_windows() -> bool:
    return sys.platform == "win32"


def rebuild_library_in_app(
    cleaned_xml_path: Path,
    itunes_dir: Path | None = None,
    on_step: Callable[[str], None] | None = None,
) -> RebuildResult:
    """Gets the cleaned XML showing in iTunes's own Library/Music view via
    the file-swap method -- the only one that actually works on classic
    Windows iTunes (see module docstring): quit iTunes, back up the
    existing iTunes Library.itl/.xml (timestamped, never deleted), copy
    the cleaned XML in as "iTunes Library.xml", and relaunch. The user
    still has to click "Choose Library..." themselves afterward, since
    Windows has no supported way to script that dialog.

    (Removed in 1.6.6-pre: this used to try a live COM import first --
    see the old core/itunes_com_sync.import_cleaned_xml_live, deleted
    along with this call site -- but classic Windows iTunes has no
    scriptable way to import a Library.xml into a running app at all, so
    that attempt failed 100% of the time on every real machine and just
    added a wasted extra launch/quit cycle before falling through to this
    same file-swap path anyway. This function now goes straight here.)

    `on_step`, if given, is called with one of the REBUILD_STEPS values
    right before that step of the sequence starts, so a caller (e.g. a
    background worker) can drive a step tracker in the UI. Purely
    additive/optional -- omitting it changes nothing about the rebuild
    itself, same as before this parameter existed.

    Never raises; every failure mode is reported in the returned
    RebuildResult so the caller can show it without a try/except of its
    own.
    """
    itunes_dir = itunes_dir or default_itunes_dir()

    def _step(name: str) -> None:
        if on_step is not None:
            on_step(name)

    if not is_windows():
        return RebuildResult(ok=False, message="This only works on Windows (classic iTunes).")

    if not cleaned_xml_path.exists():
        return RebuildResult(ok=False, message=f"Could not find the cleaned XML at:\n{cleaned_xml_path}")

    if not itunes_dir.exists():
        return RebuildResult(
            ok=False,
            message=(
                f"Could not find an iTunes folder at:\n{itunes_dir}\n\n"
                "Double check this is the folder containing your real iTunes "
                "Library.itl (e.g. on an external drive, it won't be under "
                "your user profile's Music folder)."
            ),
        )

    warnings: list[str] = []
    stamp = datetime.datetime.now().strftime(_BACKUP_STAMP_FORMAT)

    _step(STEP_QUITTING)
    itunes_quit_confirmed = _quit_itunes()
    if not itunes_quit_confirmed:
        return RebuildResult(
            ok=False,
            message=(
                "iTunes is still running and didn't close within the wait "
                "time, so nothing was changed -- rebuilding while it's still "
                "open would let it recreate the .itl file before the "
                "\"Choose Library...\" prompt can appear.\n\n"
                "Close iTunes completely (check it's not still in the "
                "taskbar/system tray) and try again."
            ),
            warnings=warnings,
        )

    itl_path = itunes_dir / "iTunes Library.itl"
    xml_path = itunes_dir / "iTunes Library.xml"
    itl_backup_path = None
    xml_backup_path = None

    _step(STEP_BACKING_UP)
    try:
        if itl_path.exists():
            itl_backup_path = itunes_dir / f"iTunes Library.itl.bak_{stamp}"
            shutil.copy2(itl_path, itl_backup_path)
            itl_path.unlink()
            # Only the most recent .itl backup is kept -- see
            # _prune_old_backups.
            _prune_old_backups(itunes_dir, "iTunes Library.itl.bak_*", "iTunes Library.itl.bak_", itl_backup_path)
    except OSError as exc:
        return RebuildResult(
            ok=False,
            message=(
                f"Could not back up/remove the existing iTunes Library.itl: {exc}\n\n"
                "iTunes may still be running or a file handle is stuck open -- "
                "close it manually and try again, or use the generated .bat script "
                "instead."
            ),
            warnings=warnings,
        )

    # Hard verification, not an assumption: if the .itl is somehow still
    # present at this point (a stuck handle, another process recreating
    # it, etc.), relaunching now would just have iTunes open that file
    # normally instead of showing "Choose Library..." -- exactly the
    # failure this function exists to prevent. Stop here rather than
    # relaunch into a no-op.
    if itl_path.exists():
        return RebuildResult(
            ok=False,
            message=(
                "iTunes Library.itl is still present after attempting to remove "
                "it, so iTunes would not have prompted to choose a library on "
                "relaunch -- nothing was relaunched. Make sure iTunes is fully "
                "closed (check Task Manager for iTunes.exe / iTunesHelper.exe) "
                "and try again."
            ),
            itl_backup_path=itl_backup_path,
            xml_backup_path=xml_backup_path,
        )

    try:
        if xml_path.exists():
            xml_backup_path = itunes_dir / f"iTunes Library.xml.bak_{stamp}"
            shutil.copy2(xml_path, xml_backup_path)
            # Only the most recent .xml backup is kept -- see
            # _prune_old_backups.
            _prune_old_backups(itunes_dir, "iTunes Library.xml.bak_*", "iTunes Library.xml.bak_", xml_backup_path)
    except OSError as exc:
        warnings.append(f"Could not back up the existing iTunes Library.xml: {exc}")

    # Clear out any *other* .xml files left in the iTunes folder before
    # relaunch (e.g. a stray manual export, or a leftover from a previous
    # run) -- same reasoning as the .itl removal above: a folder with more
    # than one .xml sitting in it can make iTunes's own library picker
    # ambiguous about what to import, or get accidentally picked up
    # instead of the cleaned file this function just wrote. Each one is
    # backed up (never deleted outright) and then removed from the live
    # folder; this only touches iTunes_dir itself, not subfolders, and
    # skips the main iTunes Library.xml (handled above) and anything
    # that's already one of our own timestamped backups.
    extra_xml_backups: dict[Path, Path] = {}
    try:
        stray_xml_files = sorted(
            p for p in itunes_dir.glob("*.xml")
            if p.is_file()
            and p.name != "iTunes Library.xml"
            # Never sweep up the cleaned XML itself. If the user saved
            # their cleaned/deduplicated output directly inside the
            # iTunes folder, resolving both paths and comparing is the
            # only reliable way to exclude it -- comparing by name alone
            # (as before) missed this case entirely, silently backing up
            # and deleting the very file the copy step below needs a
            # moment later, which surfaced as a confusing "could not copy
            # the cleaned XML" / WinError 2 failure even though the file
            # was never actually moved by the user.
            and p.resolve() != cleaned_xml_path.resolve()
        )
    except OSError as exc:
        stray_xml_files = []
        warnings.append(f"Could not scan the iTunes folder for other .xml files: {exc}")

    for stray_path in stray_xml_files:
        try:
            backup_path = itunes_dir / f"{stray_path.name}.bak_{stamp}"
            shutil.copy2(stray_path, backup_path)
            stray_path.unlink()
            extra_xml_backups[stray_path] = backup_path
            # Only the most recent backup of this particular stray file
            # (matched by its own original name) is kept -- see
            # _prune_old_backups. Scoped per stray filename rather than
            # globally, so backing up "Some Old Export.xml" doesn't delete
            # an unrelated stray file's own backup.
            _prune_old_backups(
                itunes_dir, f"{stray_path.name}.bak_*", f"{stray_path.name}.bak_", backup_path
            )
        except OSError as exc:
            warnings.append(f"Could not clear stray XML file '{stray_path.name}': {exc}")

    # Copy to a temp file in the same folder first, verify it actually
    # landed with the expected size, then atomically rename it into place
    # as "iTunes Library.xml" -- never write straight to xml_path. A
    # direct copy2() that fails or gets interrupted partway (a stuck AV
    # scan, a sync client grabbing the file mid-write, etc.) can leave
    # xml_path missing or truncated; relaunching iTunes at that point has
    # it "rebuild" a blank library instead of the cleaned one, which is
    # the exact failure this guards against. os.replace() on the same
    # volume is atomic on Windows -- there's no window where xml_path
    # exists but is only partially written.
    # Re-check right before the copy, not just at the top of this
    # function: the .itl removal and stray-XML sweep above both touch
    # files in this same folder, so if cleaned_xml_path itself somehow
    # lives inside itunes_dir and still got missed by the exclusion above
    # (or was removed by something external in the moments since this
    # function started), fail with a clear, specific message here rather
    # than a generic WinError 2 with no indication of which side --
    # source or destination -- was the problem.
    if not cleaned_xml_path.exists():
        return RebuildResult(
            ok=False,
            message=(
                f"The cleaned XML at:\n{cleaned_xml_path}\n\n"
                "is no longer there -- it disappeared after this rebuild "
                "started (not before). Nothing in the iTunes folder was "
                "changed by this step. Re-run \"Delete duplicates...\" to "
                "produce a fresh cleaned file, then Rebuild again "
                "immediately afterward."
            ),
            itl_backup_path=itl_backup_path,
            xml_backup_path=xml_backup_path,
            warnings=warnings,
            extra_xml_backups=extra_xml_backups,
        )

    _step(STEP_COPYING)
    tmp_xml_path = itunes_dir / f".iTunes Library.xml.tmp_{stamp}"
    try:
        shutil.copy2(cleaned_xml_path, tmp_xml_path)
        expected_size = cleaned_xml_path.stat().st_size
        actual_size = tmp_xml_path.stat().st_size
        if actual_size != expected_size:
            raise OSError(
                f"copied file size ({actual_size} bytes) doesn't match the "
                f"source ({expected_size} bytes)"
            )
        tmp_xml_path.replace(xml_path)
    except OSError as exc:
        try:
            if tmp_xml_path.exists():
                tmp_xml_path.unlink()
        except OSError:
            pass
        return RebuildResult(
            ok=False,
            message=(
                f"Could not copy the cleaned XML into the iTunes folder: {exc}\n\n"
                "Nothing was relaunched, and no half-written iTunes Library.xml "
                "was left behind -- your backups are untouched. Try again; if "
                "this keeps happening, check whether antivirus or a sync tool "
                "(OneDrive, Dropbox) is watching that folder and pause it."
            ),
            itl_backup_path=itl_backup_path,
            xml_backup_path=xml_backup_path,
            warnings=warnings,
            extra_xml_backups=extra_xml_backups,
        )

    # Second hard check, mirroring the .itl verification above: if
    # anything managed to remove/replace xml_path again in the instant
    # between the atomic rename and here, relaunching would still walk
    # into the same "blank library" failure. Stop rather than proceed on
    # an assumption.
    if not xml_path.exists() or xml_path.stat().st_size != expected_size:
        return RebuildResult(
            ok=False,
            message=(
                "iTunes Library.xml did not verifiably land in the iTunes "
                "folder after the copy, so iTunes was not relaunched -- "
                "relaunching now would have risked rebuilding a blank "
                "library instead of your cleaned one. Nothing else was "
                "changed; try again."
            ),
            itl_backup_path=itl_backup_path,
            xml_backup_path=xml_backup_path,
            warnings=warnings,
            extra_xml_backups=extra_xml_backups,
        )

    _step(STEP_RELAUNCHING)
    itunes_exe = find_itunes_exe()
    relaunched = False
    if itl_path.exists():
        warnings.append(
            "iTunes Library.itl reappeared before relaunch (possibly another "
            "process), so iTunes was not relaunched automatically -- launch it "
            "yourself (hold Shift) to get the \"Choose Library...\" prompt."
        )
    elif itunes_exe is not None:
        try:
            subprocess.Popen([str(itunes_exe)])
            relaunched = True
        except OSError as exc:
            warnings.append(f"Could not relaunch iTunes automatically: {exc}")
    else:
        warnings.append("Could not find iTunes.exe automatically -- launch it yourself (hold Shift).")

    message = (
        f"Backed up and replaced iTunes Library.xml in:\n{itunes_dir}\n\n"
        "iTunes should now be reopening and asking you to choose a library. "
        "Click \"Choose Library...\", select that same folder, and manually "
        "import the deduped XML you just cleaned up -- this last step has to "
        "be done by hand, since Windows has no way to automate that click."
    )
    if not relaunched:
        message += (
            "\n\niTunes could not be relaunched automatically -- open it yourself "
            "(hold Shift while launching), then do the same: choose that folder "
            "and import the deduped XML."
        )

    return RebuildResult(
        ok=True,
        message=message,
        itl_backup_path=itl_backup_path,
        xml_backup_path=xml_backup_path,
        itunes_relaunched=relaunched,
        warnings=warnings,
        extra_xml_backups=extra_xml_backups,
    )
