"""
Tests for the pluggable duplicate-detection strategies (src/core/
duplicate_strategies.py). Uses small in-memory Library/Track fixtures
(not the shared Library.xml fixture) so each strategy's behavior can be
tested in isolation from the others.

Run with: python3 -m pytest tests/test_duplicate_strategies.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.itunes_xml import Library, Track
from src.core.duplicate_detector import (
    TIER_EXACT,
    TIER_HIGH_CONFIDENCE,
    TIER_NEEDS_REVIEW,
    find_all_candidate_groups,
)
from src.core.duplicate_strategies import (
    CompositeDuplicateStrategy,
    ExactDuplicateStrategy,
    FingerprintDuplicateStrategy,
    FuzzyDuplicateStrategy,
    TIER_FINGERPRINT,
    default_strategy_pipeline,
)


def _track(track_id: int, **fields) -> Track:
    raw = {"Track ID": track_id, "Name": "", "Artist": ""}
    raw.update(fields)
    return Track(track_id=track_id, raw=raw)


def _lib(*tracks: Track) -> Library:
    return Library(raw={}, tracks={t.track_id: t for t in tracks}, playlists=[])


def test_exact_strategy_matches_find_duplicate_groups():
    lib = _lib(
        _track(1, Name="Redbone", Artist="Childish Gambino"),
        _track(2, Name="Redbone", Artist="Childish Gambino"),
        _track(3, Name="Home", Artist="Edward Sharpe"),
    )
    groups = ExactDuplicateStrategy().find_groups(lib)
    assert len(groups) == 1
    assert groups[0].tier == TIER_EXACT
    assert {t.track_id for t in groups[0].tracks} == {1, 2}


def test_exact_strategy_respects_already_grouped_ids():
    lib = _lib(
        _track(1, Name="Redbone", Artist="Childish Gambino"),
        _track(2, Name="Redbone", Artist="Childish Gambino"),
    )
    groups = ExactDuplicateStrategy().find_groups(lib, already_grouped_ids={2})
    # Only one track remains eligible -- can't form a duplicate group alone.
    assert groups == []


def test_fuzzy_strategy_matches_find_fuzzy_candidate_groups():
    lib = _lib(
        _track(1, Name="Blinding Lights", Artist="The Weeknd"),
        _track(2, Name="Blinding Light", Artist="The Weeknd"),
    )
    groups = FuzzyDuplicateStrategy().find_groups(lib)
    assert len(groups) == 1
    assert groups[0].tier in (TIER_HIGH_CONFIDENCE, TIER_NEEDS_REVIEW)


def test_fuzzy_strategy_custom_thresholds_are_passed_through():
    lib = _lib(
        _track(1, Name="Song A", Artist="Artist"),
        _track(2, Name="Song B", Artist="Artist"),
    )
    # Way below any realistic similarity for "Song A" vs "Song B" -- forces
    # a match to prove low_confidence is actually being honored, not just
    # accepted and ignored.
    strategy = FuzzyDuplicateStrategy(low_confidence=0.01, high_confidence=0.02)
    groups = strategy.find_groups(lib)
    assert len(groups) == 1


def test_fingerprint_strategy_matches_on_persistent_id():
    lib = _lib(
        _track(1, Name="Totally Different Title", Artist="A", **{"Persistent ID": "ABC123"}),
        _track(2, Name="Completely Other Name", Artist="B", **{"Persistent ID": "ABC123"}),
        _track(3, Name="Unrelated", Artist="C", **{"Persistent ID": "XYZ999"}),
    )
    groups = FingerprintDuplicateStrategy().find_groups(lib)
    assert len(groups) == 1
    assert groups[0].tier == TIER_FINGERPRINT
    assert {t.track_id for t in groups[0].tracks} == {1, 2}


def test_fingerprint_strategy_falls_back_to_size_and_duration():
    lib = _lib(
        _track(1, Name="A", Artist="X", Size=1000, **{"Total Time": 5000}),
        _track(2, Name="B", Artist="Y", Size=1000, **{"Total Time": 5000}),
        _track(3, Name="C", Artist="Z", Size=2000, **{"Total Time": 5000}),
    )
    groups = FingerprintDuplicateStrategy().find_groups(lib)
    assert len(groups) == 1
    assert {t.track_id for t in groups[0].tracks} == {1, 2}


def test_fingerprint_strategy_skips_tracks_without_signal():
    lib = _lib(_track(1, Name="A", Artist="X"), _track(2, Name="B", Artist="Y"))
    groups = FingerprintDuplicateStrategy().find_groups(lib)
    assert groups == []


def test_fingerprint_strategy_never_returns_singleton_group():
    lib = _lib(_track(1, Name="A", Artist="X", **{"Persistent ID": "ONLYONE"}))
    groups = FingerprintDuplicateStrategy().find_groups(lib)
    assert groups == []


def test_composite_strategy_claims_prevent_double_counting():
    lib = _lib(
        _track(1, Name="Redbone", Artist="Childish Gambino"),
        _track(2, Name="Redbone", Artist="Childish Gambino"),
    )
    # Fingerprint runs after exact and shares no signal here, so exact
    # should claim the pair and fingerprint should find nothing left.
    composite = CompositeDuplicateStrategy(
        [ExactDuplicateStrategy(), FingerprintDuplicateStrategy()]
    )
    groups = composite.run(lib)
    assert len(groups) == 1
    assert groups[0].tier == TIER_EXACT


def test_composite_strategy_runs_all_strategies_when_disjoint():
    lib = _lib(
        _track(1, Name="Redbone", Artist="Childish Gambino"),
        _track(2, Name="Redbone", Artist="Childish Gambino"),
        _track(3, Name="Totally Different", Artist="A", **{"Persistent ID": "SHARED"}),
        _track(4, Name="Something Else", Artist="B", **{"Persistent ID": "SHARED"}),
    )
    composite = CompositeDuplicateStrategy(
        [ExactDuplicateStrategy(), FingerprintDuplicateStrategy()]
    )
    groups = composite.run(lib)
    tiers = sorted(g.tier for g in groups)
    assert tiers == sorted([TIER_EXACT, TIER_FINGERPRINT])


def test_default_strategy_pipeline_matches_find_all_candidate_groups():
    lib = _lib(
        _track(1, Name="Redbone", Artist="Childish Gambino"),
        _track(2, Name="Redbone", Artist="Childish Gambino"),
        _track(3, Name="Blinding Lights", Artist="The Weeknd"),
        _track(4, Name="Blinding Light", Artist="The Weeknd"),
    )
    pipeline_groups = default_strategy_pipeline().run(lib)
    direct_groups = find_all_candidate_groups(lib)

    def _summary(groups):
        return sorted(
            (g.tier, tuple(sorted(t.track_id for t in g.tracks)))
            for g in groups
        )

    assert _summary(pipeline_groups) == _summary(direct_groups)


def test_default_strategy_pipeline_forwards_parallel_and_budget_kwargs():
    lib = _lib(
        _track(1, Name="Redbone", Artist="Childish Gambino"),
        _track(2, Name="Redbone", Artist="Childish Gambino"),
    )
    # parallel=True with only one/two tracks should still behave correctly
    # (find_fuzzy_candidate_groups only actually spins up a process pool
    # when there's more than one batch -- see its own guard) and, more
    # importantly, must not raise.
    pipeline = default_strategy_pipeline(parallel=True, time_budget_seconds=5.0)
    groups = pipeline.run(lib)
    assert len(groups) == 1
    assert groups[0].tier == TIER_EXACT
