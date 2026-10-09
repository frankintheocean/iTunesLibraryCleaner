"""
Covers two things added/changed in v2.2:

1. The new "Select all (incl. review)" behavior: unlike the existing
   "Select all (exact + high confidence)" checkbox (which deliberately
   skips TIER_NEEDS_REVIEW/TIER_DURATION_MISMATCH groups -- see
   DuplicateGroup.needs_review and MainWindow._on_select_all), the new
   control must select every group regardless of tier. The UI wiring
   itself lives in src/ui/main_window.py and isn't exercised directly
   here (this suite tests core logic, not Qt widgets, consistent with
   the rest of tests/), but the tier-membership rule it relies on --
   "needs_review is independent of which/how-many groups exist" -- is
   covered at the DuplicateGroup level below.

2. Large-library behavior (30,000+ tracks): confirms the streaming
   plist parser (core/plist_stream.py) and duplicate detection
   (core/duplicate_detector.py) -- both already optimized for large
   libraries in earlier releases (see their module docstrings) --
   still produce correct results and complete in bounded time at this
   scale, rather than only being covered by the small fixture library
   used elsewhere in tests/.
"""

from __future__ import annotations

import io
import time
from datetime import datetime, timezone

import plistlib
import pytest

from src.core.itunes_xml import Library
from src.core.duplicate_detector import (
    find_duplicate_groups,
    find_all_candidate_groups,
    TIER_EXACT,
    TIER_HIGH_CONFIDENCE,
    TIER_NEEDS_REVIEW,
)


# --------------------------------------------------------------------------
# 1. "Select all (incl. review)" tier semantics
# --------------------------------------------------------------------------

def test_needs_review_groups_exist_and_are_independently_selectable():
    """Sanity-checks the tier rule the new "Select all (incl. review)"
    button relies on: a group's `needs_review` flag depends only on its
    own tier, never on how many other groups are selected/visible, so
    a "select every visible row regardless of tier" control is safe to
    implement as a flat loop with no extra bookkeeping (matching
    MainWindow._on_select_all_everything's implementation)."""
    lib = _library_with_tracks(
        [
            _track(1, "Song A", "Artist A", "Album", 200_000),
            _track(2, "Song A", "Artist A", "Album", 200_000),  # exact dup of 1
            _track(3, "Song B", "Artist B", "Album", 200_000),
            _track(4, "Song B", "Artist B", "Album", 200_000),  # exact dup of 3
        ]
    )
    groups = find_duplicate_groups(lib)
    assert len(groups) == 2
    for g in groups:
        assert g.tier == TIER_EXACT
        assert g.needs_review is False

    # Fuzzy near-miss pair should land in NEEDS_REVIEW or HIGH_CONFIDENCE,
    # and needs_review must be computed purely from tier.
    lib2 = _library_with_tracks(
        [
            _track(5, "Midnite City", "M83", "Album", 200_000),
            _track(6, "Midnight City", "M83", "Album", 200_000),
        ]
    )
    candidates = find_all_candidate_groups(lib2)
    fuzzy = [g for g in candidates if g.tier in (TIER_NEEDS_REVIEW, TIER_HIGH_CONFIDENCE)]
    assert fuzzy, "expected the near-miss pair to surface as a fuzzy candidate"
    for g in fuzzy:
        assert g.needs_review == (g.tier == TIER_NEEDS_REVIEW)


# --------------------------------------------------------------------------
# 2. Large-library (30k+ track) load + detection
# --------------------------------------------------------------------------

def _track(tid, name, artist, album, ms, extra=None):
    d = {
        "Track ID": tid,
        "Name": name,
        "Artist": artist,
        "Album": album,
        "Total Time": ms,
        "Bit Rate": 256,
        "Play Count": 0,
        "Rating": 0,
        "Date Added": datetime(2020, 1, 1, tzinfo=timezone.utc),
        "Location": f"file://localhost/Users/test/Music/{artist}/{album}/{name}.m4a",
        "Kind": "AAC audio file",
        "Track Type": "File",
    }
    if extra:
        d.update(extra)
    return d


def _library_with_tracks(track_dicts):
    """Builds an in-memory Library (bypassing disk I/O) from raw track
    dicts, the same shape Library.load() produces, for tests that only
    need the in-memory object rather than round-tripping through XML."""
    tracks = Library.tracks_from_raw({str(t["Track ID"]): t for t in track_dicts})
    raw = {"Tracks": {str(t.track_id): t.raw for t in tracks.values()}, "Playlists": []}
    return Library(raw=raw, tracks=tracks, playlists=[])


def _build_large_plist_bytes(n_tracks: int) -> bytes:
    """Writes a synthetic Library.xml with `n_tracks` tracks, including
    a predictable number of exact-duplicate pairs, using plistlib (an
    independent code path from src/core/plist_stream.py) so the
    streaming parser is verified against a real, independently-produced
    plist rather than round-tripping through itself."""
    tracks = {}
    tid = 1
    # Every 10th "song index" is duplicated once, so we know exactly how
    # many exact-match groups to expect back.
    n_songs = n_tracks // 2
    for song_idx in range(n_songs):
        name = f"Song {song_idx}"
        artist = f"Artist {song_idx % 500}"
        for _copy in range(2):  # every song appears twice => all exact dups
            tracks[str(tid)] = _track(tid, name, artist, "Album", 200_000 + song_idx)
            tid += 1

    root = {
        "Major Version": 1,
        "Minor Version": 1,
        "Application Version": "1.0",
        "Tracks": tracks,
        "Playlists": [],
    }
    buf = io.BytesIO()
    plistlib.dump(root, buf, fmt=plistlib.FMT_XML, sort_keys=False)
    return buf.getvalue()


@pytest.mark.parametrize("n_tracks", [30_000])
def test_large_library_loads_correctly_and_within_time_budget(n_tracks, tmp_path):
    xml_bytes = _build_large_plist_bytes(n_tracks)
    path = tmp_path / "Library.xml"
    path.write_bytes(xml_bytes)

    start = time.monotonic()
    lib = Library.load(path)
    elapsed = time.monotonic() - start

    assert len(lib.tracks) == n_tracks
    # Generous ceiling for CI/dev-machine variance -- this is a
    # regression guard against reintroducing an O(n^2) or double-parse
    # path, not a tight performance benchmark.
    assert elapsed < 30, f"loading {n_tracks} tracks took {elapsed:.1f}s, expected < 30s"

    # library.raw["Tracks"] must be fully repopulated (see
    # core/plist_stream.py docstring) -- not left as None placeholders.
    assert all(v is not None for v in lib.raw["Tracks"].values())


def test_large_library_duplicate_detection_within_time_budget(tmp_path):
    n_tracks = 30_000
    xml_bytes = _build_large_plist_bytes(n_tracks)
    path = tmp_path / "Library.xml"
    path.write_bytes(xml_bytes)
    lib = Library.load(path)

    start = time.monotonic()
    groups = find_duplicate_groups(lib)
    elapsed = time.monotonic() - start

    # Every song in _build_large_plist_bytes appears exactly twice, so
    # every song should form exactly one exact-match duplicate group.
    expected_groups = n_tracks // 2
    assert len(groups) == expected_groups
    assert all(g.tier == TIER_EXACT for g in groups)
    # The exact-match pass is a single dict-keyed grouping (not the
    # pairwise fuzzy pass), so it should be fast even at this scale;
    # generous ceiling for the same reason as above.
    assert elapsed < 30, f"detection over {n_tracks} tracks took {elapsed:.1f}s"
