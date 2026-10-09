"""
Actionable-error-message helper.

Existing failure paths (library load, plan apply) already surface a raw
exception string via QMessageBox.critical(...). That tells the user
*that* something failed but not *what to do about it*. This module adds a
short, situation-specific "what to try next" line appended to those
messages, without changing what's raised or how control flow works
anywhere else.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# User-facing sanitization (v1.7.1-pre)
#
# The keyword matching below (RECOVERY_HINTS) already looks for technical
# substrings like "winerror 5" or "access is denied" so it can offer the
# right recovery hint -- but until now the *raw* matched text (WinError
# codes, COM HRESULTs, Python exception class names, traceback-style
# "OSError: [WinError 5] ..." fragments) was left in the message itself and
# shown verbatim in the popup. That's meaningful to a developer and noise to
# almost everyone else. sanitize_for_display() strips that technical detail
# out of the text a dialog actually shows; callers are expected to log the
# original, untouched string via error_log.log_error separately so nothing
# is lost -- it's just moved out of the popup and into the log file.
# ---------------------------------------------------------------------------

# Matches the technical prefix/suffix patterns this app's own error strings
# tend to produce when an OSError/COM exception is interpolated in with an
# f-string (e.g. "...: [WinError 5] Access is denied: 'C:\\...'" or
# "...: (-2147352567, 'Exception occurred.', (0, 'iTunesLib', ...))"). Each
# pattern is applied independently so multiple technical fragments in one
# message (rare, but possible when a low-level error is itself re-wrapped)
# are all removed, not just the first match.
_TECHNICAL_FRAGMENT_PATTERNS: list["re.Pattern[str]"] = [
    # "[WinError 5] Access is denied" / "[Errno 2] No such file or directory"
    re.compile(r"\[(?:WinError|Errno)\s+-?\d+\][^\n]*"),
    # Bare "WinError 5" / "errno 2" mentions outside brackets.
    re.compile(r"\b(?:WinError|errno)\s+-?\d+\b", re.IGNORECASE),
    # COM HRESULT tuples, e.g. (-2147352567, 'Exception occurred.', (0, ...))
    # pywin32's com_error tuples nest a second parenthesized tuple inside
    # the outer one, so this is matched greedily to end-of-line (rather
    # than the first, inner ")") to consume the whole thing in one pass.
    re.compile(r"\(-?\d{6,},[^\n]*\)"),
    # Bare hex HRESULT values, e.g. 0x80020009
    re.compile(r"\b0x[0-9A-Fa-f]{6,8}\b"),
    # A raw KeyError/IndexError repr's own bare quoted-or-numeric key/index
    # (e.g. "KeyError: 42" or "KeyError: 'snapshot_id'"), together with the
    # exception-class prefix itself -- both are internal identifiers with
    # no actionable meaning to someone reading a popup. Matched together so
    # only the class name is never left dangling in front of its own value.
    re.compile(r"\b(?:KeyError|IndexError)\s*:\s*(?:'[^'\n]*'|\d+)"),
    # Leading Python exception class name from a raw str(exc)/repr(exc),
    # e.g. "PermissionError: ..." or "com_error: ...".
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception|com_error)\s*:\s*"),
]

# Once a technical fragment is stripped out, str(exc) interpolations often
# leave behind orphaned punctuation/whitespace ("...: : 'C:\\...'" or a
# trailing ": " with nothing after it). Cleaned up so the remaining message
# still reads as a normal sentence.
_ORPHAN_PUNCTUATION = re.compile(r"[ \t]*:[ \t]*(?=[:\n]|$)")
_MULTI_BLANK_LINES = re.compile(r"\n{3,}")
_TRAILING_PUNCT_WHITESPACE = re.compile(r"[ \t]+\n")


def sanitize_for_display(message: str) -> str:
    """Strips WinError/errno codes, COM HRESULT tuples/hex codes, and raw
    Python exception-class prefixes out of a message before it's shown in a
    user-facing dialog. Returns plain, non-technical text; callers should
    log the original unmodified `message` (e.g. via error_log.log_error)
    before calling this, so the technical detail is still available for
    troubleshooting -- just in the log file instead of the popup."""
    text = message
    for pattern in _TECHNICAL_FRAGMENT_PATTERNS:
        text = pattern.sub("", text)
    text = _ORPHAN_PUNCTUATION.sub("", text)
    text = _TRAILING_PUNCT_WHITESPACE.sub("\n", text)
    text = _MULTI_BLANK_LINES.sub("\n\n", text)
    # Collapse any run of plain spaces/tabs left behind by a removed
    # mid-sentence fragment (e.g. "folder  because" -> "folder because"),
    # without touching newlines/paragraph breaks.
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()

# Keywords matched as whole words (via regex word boundaries), not bare
# substrings. Plain `kw in lowered` previously let short/common keywords
# (e.g. "tracks", "xml", "plist") false-positive-match unrelated error
# text that happens to contain that word -- this app's own normal
# messages routinely mention "tracks" ("cannot repoint 5 tracks..."),
# and "xml"/"plist" appear outside the specific corrupted-library error
# they were meant to catch (e.g. "audit report is not valid xml").
# \b works correctly here since every keyword is ASCII alphanumeric/space;
# multi-word phrases still match as a literal (word-bounded) sequence.
_WORD_BOUNDARY_CACHE: dict[str, "re.Pattern[str]"] = {}


def _keyword_pattern(keyword: str) -> "re.Pattern[str]":
    pattern = _WORD_BOUNDARY_CACHE.get(keyword)
    if pattern is None:
        pattern = re.compile(r"\b" + re.escape(keyword) + r"\b")
        _WORD_BOUNDARY_CACHE[keyword] = pattern
    return pattern


RECOVERY_HINTS: list[tuple[tuple[str, ...], str]] = [
    (
        ("permission denied", "winerror 5", "access is denied"),
        "The file may be open in iTunes/Apple Music or another program, or "
        "you may not have write access to that folder. Close any app that "
        "has the file open, or choose a different save location, then try "
        "again.",
    ),
    (
        ("no such file", "cannot find the file", "winerror 2", "filenotfound"),
        "The file may have been moved, renamed, or deleted since it was "
        "selected. Use Open Library.xml\u2026 to point at its current "
        "location.",
    ),
    (
        ("not look like an itunes library", "missing top-level"),
        "Re-export the library from iTunes/Apple Music via "
        "File \u2192 Library \u2192 Export Library\u2026, then open the newly "
        "exported Library.xml (not a playlist-only export).",
    ),
    (
        # "xml"/"plist" deliberately excluded: both appear as ordinary
        # words in plenty of unrelated app text (e.g. "audit report is
        # not valid xml", "could not initialize plist cache directory")
        # that has nothing to do with a corrupted Library.xml. The two
        # keywords below already uniquely match the one real source
        # message (itunes_xml.py's "Could not parse '<file>' as an
        # iTunes XML library plist: <exc>", plus the underlying XML
        # parser's own "not well-formed" wording when it bubbles into
        # <exc>), so nothing more specific is needed.
        ("could not parse", "not well-formed"),
        "The file may be incomplete (e.g. copied while iTunes was still "
        "writing it) or corrupted. Re-export the library and try again, "
        "and make sure the export finished fully before selecting it.",
    ),
    (
        ("disk", "no space", "enospc"),
        "There may not be enough free disk space to save this file. Free "
        "up space or choose a save location on a different drive, then try "
        "again.",
    ),
    (
        ("no known source file",),
        "This library wasn't loaded from a file on disk (e.g. it was "
        "restored from a backup snapshot), so there's no original file to "
        "write back to. Use Save As / choose a new file location instead.",
    ),
]

_DEFAULT_HINT = (
    "Your original library file has not been modified. Check that the file "
    "isn't open in another program and that you have permission to read/"
    "write it, then try again. If this keeps happening, use Help \u2192 "
    "What's new\u2026 to confirm you're on the latest version."
)


def with_recovery_guidance(message: str) -> str:
    """Appends a short, situation-specific recovery hint to an error
    message, matched by keyword against the lowercased text. Falls back to
    a general-purpose hint if nothing more specific matches, so every
    error dialog gives the user a concrete next step rather than just the
    raw exception text.

    Keyword matching runs against the original `message` (technical terms
    like "winerror 5" are exactly what the keywords look for), but the
    message text actually returned is sanitized via sanitize_for_display()
    first -- so the dialog gets the hint without the WinError code/COM
    detail that triggered it. Callers that want that raw detail preserved
    for troubleshooting should log `message` as-is (e.g. via
    error_log.log_error) before calling this, since it's not included in
    the return value."""
    lowered = message.lower()
    display_message = sanitize_for_display(message)
    for keywords, hint in RECOVERY_HINTS:
        if any(_keyword_pattern(kw).search(lowered) for kw in keywords):
            return f"{display_message}\n\nWhat to try:\n{hint}"
    return f"{display_message}\n\nWhat to try:\n{_DEFAULT_HINT}"
