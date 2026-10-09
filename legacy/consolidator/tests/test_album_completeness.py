"""
Tests for v2.1's "complete album copy replaces incomplete duplicate"
auto-selection (src/core/duplicate_detector.find_incomplete_album_overlap_track_ids
and its wiring into core/consolidator.build_plan's MergeAction.incomplete_album_overlap).

Uses small in-memory Library/Track fixtures (not the shared Library.xml
fixture), matching tests/test_duplicate_strategies.py's convention, so
each scenario is isolated and easy to reason about.

Run with: python3 -m pytest tests/test_album_completeness.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.itunes_xml import Library, Track
from src.core.duplicate_detector import (
    find_all_candidate_groups,
    find_incomplete_album_overlap_track_ids,
)
from src.core.consolidator import build_plan


def _track(track_id: int, **fields) -> Track:
    raw = {"Track ID": track_id, "Name": "", "Artist": ""}
    raw.update(fields)
    return Track(track_id=track_id, raw=raw)


def _lib(*tracks: Track) -> Library:
    return Library(raw={}, tracks={t.track_id: t for t in tracks}, playlists=[])


def _album_pair(
    complete_track_count=4,
    incomplete_track_count=4,
    declared_complete=4,
    declared_incomplete=4,
    bitrate_complete=320,
    bitrate_incomplete=128,
    overlap_titles=("Track One", "Track Two", "Track Three"),
    id_start=1,
):
    """Builds two "copies" of the same album: a complete copy with
    `complete_track_count` tracks (bitrate_complete) and an incomplete
    copy with `incomplete_track_count` tracks (bitrate_incomplete),
    sharing `overlap_titles` as duplicate songs between them. Both
    copies' tracks are tagged with the given declared Track Count."""
    tracks = []
    tid = id_start
    for i, title in enumerate(overlap_titles):
        tracks.append(_track(
            tid, Name=title, Artist="Artist", Album="Album X",
        ))
        tid += 1
    # pad the complete copy up to complete_track_count with unique titles
    for i in range(len(overlap_titles), complete_track_count):
        tracks.append(_track(
            tid, Name=f"Complete Only {i}", Artist="Artist", Album="Album X",
        ))
        tid += 1
    for t in tracks[:complete_track_count]:
        t.raw["Bit Rate"] = bitrate_complete
        if declared_complete is not None:
            t.raw["Track Count"] = declared_complete
    complete_tracks = tracks[:complete_track_count]

    incomplete_tracks = []
    for i, title in enumerate(overlap_titles):
        incomplete_tracks.append(_track(
            tid, Name=title, Artist="Artist", Album="Album X",
        ))
        tid += 1
    for i in range(len(overlap_titles), incomplete_track_count):
        incomplete_tracks.append(_track(
            tid, Name=f"Incomplete Only {i}", Artist="Artist", Album="Album X",
        ))
        tid += 1
    for t in incomplete_tracks[:incomplete_track_count]:
        t.raw["Bit Rate"] = bitrate_incomplete
        if declared_incomplete is not None:
            t.raw["Track Count"] = declared_incomplete
    incomplete_tracks = incomplete_tracks[:incomplete_track_count]

    return complete_tracks, incomplete_tracks


def test_track_count_property_reads_tag():
    t = _track(1, **{"Track Count": 12})
    assert t.track_count == 12


def test_track_count_property_missing_or_invalid():
    assert _track(1).track_count is None
    assert _track(1, **{"Track Count": 0}).track_count is None
    assert _track(1, **{"Track Count": "not a number"}).track_count is None


def test_declared_track_count_flags_incomplete_overlap():
    # Complete copy: 6 tracks, Track Count tag says 6 (complete).
    # Incomplete copy: 3 tracks, Track Count tag says 6 (incomplete: only
    # has half the declared album).
    complete, incomplete = _album_pair(
        complete_track_count=6, incomplete_track_count=3,
        declared_complete=6, declared_incomplete=6,
        overlap_titles=("Track One", "Track Two", "Track Three"),
    )
    lib = _lib(*complete, *incomplete)
    groups = find_all_candidate_groups(lib)
    overlap_ids = find_incomplete_album_overlap_track_ids(lib, groups)

    incomplete_overlap_ids = {t.track_id for t in incomplete}
    assert incomplete_overlap_ids <= overlap_ids
    # None of the complete copy's tracks should ever be flagged.
    complete_ids = {t.track_id for t in complete}
    assert not (complete_ids & overlap_ids)


def test_falls_back_to_comparing_actual_totals_when_no_track_count():
    # Neither copy has a Track Count tag; incomplete copy simply has
    # fewer tracks than the other.
    complete, incomplete = _album_pair(
        complete_track_count=8, incomplete_track_count=3,
        declared_complete=None, declared_incomplete=None,
        overlap_titles=("Track One", "Track Two", "Track Three"),
    )
    lib = _lib(*complete, *incomplete)
    groups = find_all_candidate_groups(lib)
    overlap_ids = find_incomplete_album_overlap_track_ids(lib, groups)

    incomplete_overlap_ids = {t.track_id for t in incomplete}
    assert incomplete_overlap_ids <= overlap_ids


def test_equal_actual_totals_with_no_track_count_is_not_flagged():
    # Same size, no Track Count anywhere -- no signal to call either copy
    # complete/incomplete, so nothing should be flagged.
    complete, incomplete = _album_pair(
        complete_track_count=4, incomplete_track_count=4,
        declared_complete=None, declared_incomplete=None,
        overlap_titles=("Track One", "Track Two", "Track Three"),
    )
    lib = _lib(*complete, *incomplete)
    groups = find_all_candidate_groups(lib)
    overlap_ids = find_incomplete_album_overlap_track_ids(lib, groups)
    assert overlap_ids == set()


def test_below_min_shared_tracks_not_flagged():
    # Only 2 tracks per copy -- below ALBUM_COMPLETENESS_MIN_TRACKS (3),
    # so this should never be flagged even though one copy is smaller.
    complete, incomplete = _album_pair(
        complete_track_count=2, incomplete_track_count=1,
        declared_complete=None, declared_incomplete=None,
        overlap_titles=("Track One",),
    )
    lib = _lib(*complete, *incomplete)
    groups = find_all_candidate_groups(lib)
    overlap_ids = find_incomplete_album_overlap_track_ids(lib, groups)
    assert overlap_ids == set()


def test_single_album_copy_not_flagged():
    tracks = [
        _track(1, Name="Track One", Artist="Artist", Album="Album X", **{"Track Count": 3}),
        _track(2, Name="Track Two", Artist="Artist", Album="Album X", **{"Track Count": 3}),
        _track(3, Name="Track Three", Artist="Artist", Album="Album X", **{"Track Count": 3}),
    ]
    lib = _lib(*tracks)
    groups = find_all_candidate_groups(lib)
    overlap_ids = find_incomplete_album_overlap_track_ids(lib, groups)
    assert overlap_ids == set()


def test_marked_not_duplicate_group_excluded():
    complete, incomplete = _album_pair(
        complete_track_count=6, incomplete_track_count=3,
        declared_complete=6, declared_incomplete=6,
        overlap_titles=("Track One", "Track Two", "Track Three"),
    )
    lib = _lib(*complete, *incomplete)
    groups = find_all_candidate_groups(lib)
    for g in groups:
        g.marked_not_duplicate = True
    overlap_ids = find_incomplete_album_overlap_track_ids(lib, groups)
    assert overlap_ids == set()


def test_merge_action_carries_incomplete_album_overlap_flag():
    complete, incomplete = _album_pair(
        complete_track_count=6, incomplete_track_count=3,
        declared_complete=6, declared_incomplete=6,
        overlap_titles=("Track One", "Track Two", "Track Three"),
    )
    lib = _lib(*complete, *incomplete)
    groups = find_all_candidate_groups(lib)
    plan = build_plan(lib, groups)

    flagged_actions = [a for a in plan.actions if a.incomplete_album_overlap]
    assert flagged_actions, "expected at least one action flagged"
    for action in flagged_actions:
        # The flag should only ever be set when a removed (duplicate)
        # track in that action actually belongs to the incomplete copy.
        incomplete_ids = {t.track_id for t in incomplete}
        assert any(rid in incomplete_ids for rid in action.removed_ids)
    # Nothing about the plan's actual removal/canonical decisions changes
    # because of this flag -- it's purely informational.
    assert plan.total_duplicates_removed == sum(len(g.duplicates()) for g in groups)


def test_no_regression_when_no_albums_present():
    # Tracks with no Album tag at all should never crash the scan and
    # should never be flagged (nothing to compare album-wise).
    lib = _lib(
        _track(1, Name="Redbone", Artist="Childish Gambino"),
        _track(2, Name="Redbone", Artist="Childish Gambino"),
    )
    groups = find_all_candidate_groups(lib)
    overlap_ids = find_incomplete_album_overlap_track_ids(lib, groups)
    assert overlap_ids == set()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
