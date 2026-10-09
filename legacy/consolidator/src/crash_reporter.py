"""
Telemetry-free crash reporter.

Writes a single self-contained crash dump file to disk for each unhandled
exception -- full traceback plus lightweight reproduction context (app
version, OS/platform, Python/Qt versions, and a short trail of recent
user actions) -- so a problem can be diagnosed from the file the user
already has, without anything ever leaving the machine.

Explicitly NOT telemetry: no network call is made anywhere in this
module, no identifiers are generated or transmitted, and nothing here
runs unless an actual crash (or startup failure) occurs. This is a
strictly local, best-effort supplement to error_log.py's existing
rolling error.log -- error_log keeps a short in-memory/on-disk trail of
*every* logged error for at-a-glance diagnostics; this module writes one
richer, standalone dump per crash, meant to be attached to a bug report
or read in full without digging through the rolling log.

Like error_log.py, this must never raise itself and never change control
flow: a failure to write a crash dump (disk full, no write permission)
is swallowed silently rather than surfacing a second error on top of the
crash already being handled.
"""

from __future__ import annotations

import os
import platform
import re
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import List, Optional

# Cap how many crash dump files accumulate on disk and how many recent
# actions are kept for repro context -- both bounded for the same reason
# error_log.py bounds its own memory buffer and file size: this is
# diagnostic data, not something that should grow without limit on a
# machine that's used regularly.
MAX_DUMP_FILES = 50
MAX_ACTION_TRAIL = 20

_dumps_dir: Optional[Path] = None
_action_trail: List[str] = []

# App version and OS/platform/Python/Qt versions are the only "identifying"
# information a dump ever contains -- no machine name, username, IP, or any
# other persistent identifier is read or written anywhere in this module.
_PII_LIKE_PATTERNS: list["re.Pattern[str]"] = [
    # Windows user profile paths (C:\Users\<name>\...) commonly appear
    # inside file-path arguments captured in a traceback (e.g. the
    # library path a user opened). Redact just the username segment so
    # the rest of the path (still useful for repro) is kept.
    re.compile(r"([A-Za-z]:\\Users\\)[^\\]+", re.IGNORECASE),
    re.compile(r"(/(?:home|Users)/)[^/]+", re.IGNORECASE),
]


def _redact(text: str) -> str:
    """Best-effort redaction of the one kind of personally-identifying
    fragment likely to appear incidentally in a path (the OS username
    segment of a home/profile directory) -- everything else in a dump
    (the exception, traceback, recent in-app actions) is already
    app-internal diagnostic text, not personal data, so nothing else is
    touched here."""
    redacted = text
    for pattern in _PII_LIKE_PATTERNS:
        redacted = pattern.sub(r"\1<user>", redacted)
    return redacted


def init(data_dir: str) -> None:
    """Point the crash reporter at the app's data directory. Called once
    from main.py, the same way and at the same point as error_log.init --
    before this runs, record_action()/write_crash_dump() below still work
    without error (they just can't persist a dump to disk yet), so a
    crash before init() can run is never itself unhandled."""
    global _dumps_dir
    try:
        dumps_dir = Path(data_dir) / "crash_dumps"
        dumps_dir.mkdir(parents=True, exist_ok=True)
        _dumps_dir = dumps_dir
    except OSError:
        _dumps_dir = None


def record_action(description: str) -> None:
    """Appends one short breadcrumb (e.g. "Opened library",
    "Clicked Clean up duplicates") to the in-memory action trail used as
    reproduction context in the next crash dump. Never raises -- a
    breadcrumb failing to record must never interrupt the action it's
    describing."""
    try:
        timestamp = time.strftime("%H:%M:%S")
        _action_trail.append(f"[{timestamp}] {description}")
        if len(_action_trail) > MAX_ACTION_TRAIL:
            del _action_trail[: len(_action_trail) - MAX_ACTION_TRAIL]
    except Exception:
        pass


def _app_version() -> str:
    try:
        from .changelog import APP_VERSION
        return APP_VERSION
    except Exception:
        return "unknown"


def _environment_block() -> str:
    lines = [
        f"App version: {_app_version()}",
        f"Platform: {platform.platform()}",
        f"Python: {platform.python_version()}",
    ]
    try:
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
        lines.append(f"PyQt6: {PYQT_VERSION_STR} (Qt {QT_VERSION_STR})")
    except Exception:
        pass
    return "\n".join(lines)


def write_crash_dump(context: str, exc: BaseException = None) -> Optional[Path]:
    """Writes one crash dump file and returns its path (or None if it
    couldn't be written -- e.g. init() was never called, or disk write
    failed). context: short description of what was happening, matching
    error_log.log_error's own `context` parameter so the two stay easy to
    cross-reference by eye. Never raises."""
    if _dumps_dir is None:
        return None
    try:
        if exc is not None:
            trace_text = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ).strip()
        else:
            trace_text = "(no exception object provided)"

        recent_actions = (
            "\n".join(f"  {a}" for a in reversed(_action_trail))
            if _action_trail
            else "  (none recorded this session)"
        )

        dump_text = (
            "iTunes Library Consolidator -- local crash dump\n"
            "This file stays on this computer. Nothing here is sent "
            "anywhere automatically -- attach it manually to a bug "
            "report if you'd like help diagnosing it.\n"
            f"{'=' * 72}\n"
            f"When: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Context: {context}\n"
            f"{_environment_block()}\n"
            f"{'=' * 72}\n"
            "Recent actions leading up to this (most recent first):\n"
            f"{recent_actions}\n"
            f"{'=' * 72}\n"
            "Traceback:\n"
            f"{trace_text}\n"
        )
        dump_text = _redact(dump_text)

        timestamp_slug = time.strftime("%Y%m%d_%H%M%S")
        unique_slug = uuid.uuid4().hex[:8]
        dump_path = _dumps_dir / f"crash_{timestamp_slug}_{unique_slug}.txt"
        with open(dump_path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(dump_text)

        _prune_old_dumps()
        return dump_path
    except Exception:
        return None


def _prune_old_dumps() -> None:
    """Deletes the oldest dump files beyond MAX_DUMP_FILES, mirroring
    error_log.py's own bounded-size approach -- crash dumps accumulate
    only from actual crashes (rare relative to every other write in this
    app), but are still capped so a machine that hits the same recurring
    bug repeatedly doesn't fill up with dumps unboundedly."""
    if _dumps_dir is None:
        return
    try:
        dumps = sorted(
            _dumps_dir.glob("crash_*.txt"), key=lambda p: p.stat().st_mtime
        )
        excess = len(dumps) - MAX_DUMP_FILES
        if excess <= 0:
            return
        for old_dump in dumps[:excess]:
            try:
                old_dump.unlink()
            except OSError:
                pass
    except OSError:
        pass


def list_crash_dumps() -> List[Path]:
    """Newest-first list of crash dump files currently on disk."""
    if _dumps_dir is None:
        return []
    try:
        return sorted(
            _dumps_dir.glob("crash_*.txt"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return []


def dumps_dir() -> Optional[Path]:
    return _dumps_dir
