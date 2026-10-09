"""
Library Health analysis.

Read-only report over a loaded Library: surfaces issues beyond exact/fuzzy
duplicates so the user can see the overall state of their metadata and
audio quality before (or instead of) running a consolidation. Nothing in
this module mutates the library — it only reads Track/Playlist fields
already present in the parsed XML, consistent with the rest of the app's
"metadata only, no audio file access" scope.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .duplicate_detector import (
    AlbumDuplicateGroup,
    DuplicateGroup,
    find_album_duplicate_groups,
    find_all_candidate_groups,
)
from .itunes_xml import Library, Track

# Bitrate (kbps) below which a lossy file is flagged as low quality. 128kbps
# is the traditional "acceptable but not great" MP3 floor; anything under
# that is a clear quality issue worth surfacing.
LOW_BITRATE_KBPS = 128

# Metadata fields considered "core" for a well-tagged track. Missing any of
# these is reported as an inconsistent/incomplete tag, not just missing
# artwork specifically.
CORE_TAG_FIELDS = ("Name", "Artist", "Album", "Genre", "Year")


@dataclass
class HealthIssueGroup:
    """One category of issue with the list of affected track ids."""
    category: str
    description: str
    track_ids: list[int] = field(default_factory=list)


@dataclass
class HealthReport:
    total_tracks: int
    duplicate_groups: list[DuplicateGroup]
    missing_artwork: list[int]
    missing_metadata: dict[str, list[int]]  # field name -> track ids missing it
    inconsistent_tags: list[int]  # missing 2+ core fields
    low_quality: list[int]  # bitrate below threshold (and > 0, i.e. known)
    unknown_quality: list[int]  # bitrate not recorded at all
    missing_or_broken_location: list[int]  # Location field absent/empty, or local file missing on disk
    estimated_duplicate_storage_bytes: int
    # Whole albums that appear to have been imported more than once at
    # different bitrates (see duplicate_detector.find_album_duplicate_groups).
    # Informational only -- the individual duplicate tracks these albums
    # are made of are already counted in duplicate_groups/duplicate_track_count
    # above via the normal per-track matching; this is an additional
    # album-level view over the same underlying duplicates.
    album_duplicate_groups: list[AlbumDuplicateGroup] = field(default_factory=list)

    @property
    def album_duplicate_track_count(self) -> int:
        return sum(g.duplicate_track_count for g in self.album_duplicate_groups)

    @property
    def duplicate_track_count(self) -> int:
        return sum(len(g.duplicates()) for g in self.duplicate_groups if not g.marked_not_duplicate)

    @property
    def issues_total(self) -> int:
        return (
            self.duplicate_track_count
            + len(self.missing_artwork)
            + len(self.inconsistent_tags)
            + len(self.low_quality)
            + len(self.missing_or_broken_location)
        )

    def estimated_storage_savings_human(self) -> str:
        return _human_bytes(self.estimated_duplicate_storage_bytes)


def _human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def _track_file_size(track: Track) -> int:
    """Size in bytes as recorded in the library metadata, if present.
    Falls back to 0 (unknown) rather than touching the filesystem, since
    the app is designed to work purely from XML metadata even when the
    referenced audio files are offline/unavailable."""
    return int(track.raw.get("Size", 0) or 0)


import time

# Hard budget on total wall-clock time spent doing os.path.exists() checks
# across one analyze_library() call. A single stat() against an
# unreachable network share or a disconnected external drive can block
# for seconds; multiplied across a large library with many such tracks,
# this previously had no bound and could visibly stall the UI (this runs
# on the GUI thread right after a load/apply completes). Once the budget
# is spent, remaining local-path tracks are simply not flagged rather
# than checked -- an undercount here is far preferable to a UI freeze.
_LOCATION_CHECK_BUDGET_SECONDS = 1.5


def _location_missing_or_unreachable(track: Track, deadline: list[float]) -> bool:
    """True if the track has no Location at all, or has one that points to
    a local file:// path that does not currently exist on disk. Files on
    a Location we can't interpret (streaming/remote URLs, cloud-only
    entries) are not flagged — we can only check what we can resolve.
    `deadline` is a 1-element list holding the monotonic time budget
    checks may run until; passed by reference so the caller's running
    total is shared across every call in one analyze_library() pass."""
    loc = track.location
    if not loc:
        return True
    if not loc.startswith("file://"):
        return False  # remote/streamed/cloud reference; nothing to check locally
    path = _file_uri_to_path(loc)
    if path is None:
        return False
    if time.monotonic() > deadline[0]:
        return False  # budget spent; don't flag rather than risk a long stat()
    try:
        return not os.path.exists(path)
    except OSError:
        return False


def _file_uri_to_path(uri: str) -> str | None:
    # Bug fix: mirrors the same Windows drive-letter fix in
    # core/artwork.file_uri_to_path -- see that function's docstring.
    # Without stripping the leading slash before a drive letter (e.g.
    # "/C:/Users/...") the os.path.exists() check below is always False
    # for a normal Windows-style Location, which flagged every track as
    # having a missing/broken file link.
    try:
        from urllib.parse import urlparse, unquote
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return None
        raw_path = unquote(parsed.path)
        if len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
            raw_path = raw_path[1:]
        return raw_path
    except Exception:
        return None


def analyze_library(
    library: Library,
    duplicate_groups: list[DuplicateGroup] | None = None,
) -> HealthReport:
    """Builds a full health report. Pass in already-computed duplicate
    groups (e.g. from the main window's plan) to avoid re-scanning; if
    omitted, this runs the same exact+fuzzy scan used elsewhere."""
    if duplicate_groups is None:
        duplicate_groups = find_all_candidate_groups(library)

    tracks = list(library.tracks.values())

    missing_artwork = [t.track_id for t in tracks if not t.raw.get("Artwork Count", 0)]

    missing_metadata: dict[str, list[int]] = {field_name: [] for field_name in CORE_TAG_FIELDS}
    inconsistent_tags: list[int] = []
    for t in tracks:
        missing_fields = [f for f in CORE_TAG_FIELDS if not t.raw.get(f)]
        for f in missing_fields:
            missing_metadata[f].append(t.track_id)
        if len(missing_fields) >= 2:
            inconsistent_tags.append(t.track_id)

    low_quality = [t.track_id for t in tracks if 0 < t.bitrate < LOW_BITRATE_KBPS]
    unknown_quality = [t.track_id for t in tracks if t.bitrate == 0]

    deadline = [time.monotonic() + _LOCATION_CHECK_BUDGET_SECONDS]
    missing_or_broken_location = [
        t.track_id for t in tracks if _location_missing_or_unreachable(t, deadline)
    ]

    # Storage savings estimate: sum of file sizes of tracks that WOULD be
    # removed by consolidating every current duplicate group (excluding any
    # the user has marked "not duplicate"), using the Size field already
    # present in the library metadata (no filesystem access required).
    savings = 0
    for g in duplicate_groups:
        if g.marked_not_duplicate:
            continue
        for dup in g.duplicates():
            savings += _track_file_size(dup)

    album_duplicate_groups = find_album_duplicate_groups(library)

    return HealthReport(
        total_tracks=len(tracks),
        duplicate_groups=duplicate_groups,
        missing_artwork=missing_artwork,
        missing_metadata=missing_metadata,
        inconsistent_tags=inconsistent_tags,
        low_quality=low_quality,
        unknown_quality=unknown_quality,
        missing_or_broken_location=missing_or_broken_location,
        estimated_duplicate_storage_bytes=savings,
        album_duplicate_groups=album_duplicate_groups,
    )
