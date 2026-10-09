"""
"What changed since last export" support.

Computes a small, JSON-serializable fingerprint of a loaded Library (one
compact record per track, not the full raw dict) and diffs two such
fingerprints to describe what changed between two exports of the same
iTunes/Apple Music library -- tracks added, tracks removed, and tracks
whose core metadata changed (name/artist/album/rating/play count), plus
playlist count deltas.

This never touches the CacheDB `snapshots` table (full-library backups
used for Restore/undo) -- it's a separate, much smaller record purely for
comparison, stored via CacheDB.get_setting/set_setting under a per-
source-path key (see ui/main_window._record_export_fingerprint and
_diff_against_last_export). Nothing here mutates a Library or reads/writes
files; it only reads Track/Library fields already parsed in memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .itunes_xml import Library

# Bumped only if the fingerprint record shape changes incompatibly; lets
# _diff_against_last_export recognize and skip a fingerprint saved by an
# older/incompatible app version instead of misreading it.
FINGERPRINT_VERSION = 1

# Track fields compared for "modified" -- deliberately a small, stable
# subset (not every raw key) so unrelated fields iTunes itself rewrites
# on every export (e.g. "Date Added" formatting, "Persistent ID" churn on
# some iTunes versions) don't produce noisy false-positive diffs.
_COMPARED_FIELDS = ("Name", "Artist", "Album", "Rating", "Play Count")


@dataclass
class LibraryDiff:
    """Result of comparing two fingerprints of the same library source."""

    previous_export_date: str | None
    added_track_ids: list[int] = field(default_factory=list)
    removed_track_ids: list[int] = field(default_factory=list)
    # (track_id, [changed_field_names]) for tracks present in both exports
    # but with a different value for at least one of _COMPARED_FIELDS.
    modified: list[tuple[int, list[str]]] = field(default_factory=list)
    playlist_count_before: int = 0
    playlist_count_after: int = 0

    @property
    def has_changes(self) -> bool:
        return bool(self.added_track_ids or self.removed_track_ids or self.modified) or (
            self.playlist_count_before != self.playlist_count_after
        )

    @property
    def playlist_count_delta(self) -> int:
        return self.playlist_count_after - self.playlist_count_before


def build_fingerprint(library: Library) -> dict:
    """Builds a compact, JSON-serializable fingerprint of `library` for
    later comparison. Deliberately small (a handful of fields per track,
    not the full raw dict) since this is stored as an ordinary UI setting
    (see CacheDB.set_setting), not a full snapshot."""
    tracks = {}
    for track_id, track in library.tracks.items():
        tracks[str(track_id)] = [track.raw.get(field) for field in _COMPARED_FIELDS]
    export_date = library.raw.get("Date")
    return {
        "version": FINGERPRINT_VERSION,
        # str(...) so this round-trips through plain JSON regardless of
        # whether the plist parser handed back a datetime (see
        # cache_db._json_default, which this deliberately doesn't reuse --
        # a fingerprint only ever needs the date for display/ordering, not
        # a faithful re-parseable datetime).
        "export_date": str(export_date) if export_date is not None else None,
        "playlist_count": len(library.playlists),
        "tracks": tracks,
    }


def diff_against_fingerprint(library: Library, previous: dict | None) -> LibraryDiff | None:
    """Compares `library`'s current state against a previously saved
    fingerprint (as returned by build_fingerprint / stored via
    CacheDB.get_setting). Returns None if there's nothing to compare
    against (no previous fingerprint, or it's from an incompatible
    version) -- distinct from a LibraryDiff with has_changes=False, which
    means "compared, and nothing changed"."""
    if not isinstance(previous, dict) or previous.get("version") != FINGERPRINT_VERSION:
        return None
    prev_tracks = previous.get("tracks")
    if not isinstance(prev_tracks, dict):
        return None

    current_ids = set(library.tracks.keys())
    prev_ids = {int(k) for k in prev_tracks.keys() if k.lstrip("-").isdigit()}

    added = sorted(current_ids - prev_ids)
    removed = sorted(prev_ids - current_ids)

    modified: list[tuple[int, list[str]]] = []
    for track_id in sorted(current_ids & prev_ids):
        prev_values = prev_tracks.get(str(track_id))
        if not isinstance(prev_values, list) or len(prev_values) != len(_COMPARED_FIELDS):
            continue
        track = library.tracks[track_id]
        changed_fields = [
            name
            for name, prev_value in zip(_COMPARED_FIELDS, prev_values)
            if track.raw.get(name) != prev_value
        ]
        if changed_fields:
            modified.append((track_id, changed_fields))

    return LibraryDiff(
        previous_export_date=previous.get("export_date"),
        added_track_ids=added,
        removed_track_ids=removed,
        modified=modified,
        playlist_count_before=int(previous.get("playlist_count") or 0),
        playlist_count_after=len(library.playlists),
    )
