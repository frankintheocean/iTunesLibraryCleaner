"""
Run with: python3 -m pytest tests/ -v
(or python3 tests/test_consolidation.py to run without pytest)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.itunes_xml import Library, Track
from src.core.duplicate_detector import (
    find_duplicate_groups,
    find_all_candidate_groups,
    find_fuzzy_candidate_groups,
    make_manual_merge_group,
    normalize,
    similarity_score,
    DuplicateGroup,
    TIER_DURATION_MISMATCH,
    TIER_EXACT,
    TIER_MANUAL,
    TIER_NEEDS_REVIEW,
)
from src.core.consolidator import build_plan, apply_plan
from src.core.library_health import analyze_library

FIXTURE = Path(__file__).parent / "fixtures" / "Library.xml"


def load():
    assert FIXTURE.exists(), "Run tests/generate_fixture.py first"
    return Library.load(FIXTURE)


def test_normalize_strips_feat_and_remaster_tags():
    assert normalize("Blinding Lights (feat. Rosalia)") == normalize("Blinding Lights")
    assert normalize("Song Title (Remastered 2011)") == normalize("Song Title")
    assert normalize("  Song   Title  ") == normalize("Song Title")


def test_library_loads_all_tracks_and_playlists():
    lib = load()
    assert len(lib.tracks) == 10
    assert len(lib.playlists) == 6
    assert len(lib.user_playlists()) == 4  # excludes Library + Music specials


def test_duplicate_groups_found_correctly():
    lib = load()
    groups = find_duplicate_groups(lib)
    # Expect exactly 3 duplicate groups: Midnight City, Blinding Lights, Redbone.
    # "Home" must NOT be grouped (different artists = different songs).
    keys = sorted(g.key for g in groups)
    assert len(groups) == 3, f"expected 3 groups, got {len(groups)}: {keys}"
    titles = sorted(g.key[1] for g in groups)
    assert titles == sorted(["midnight city", "blinding lights", "redbone"])


def test_home_tracks_not_merged_different_artists():
    lib = load()
    groups = find_duplicate_groups(lib)
    for g in groups:
        ids = {t.track_id for t in g.tracks}
        assert not ({8, 9} <= ids), "Home (Edward Sharpe) and Home (Gabrielle Aplin) must not merge"


def test_canonical_selection_picks_most_complete_highest_quality():
    lib = load()
    groups = find_duplicate_groups(lib)
    by_title = {g.key[1]: g for g in groups}

    # Blinding Lights: track 3 has artwork, 320kbps, full metadata, high rating -> canonical
    canon = by_title["blinding lights"].canonical()
    assert canon.track_id == 3, f"expected track 3 canonical, got {canon.track_id}"

    # Midnight City: track 1 has higher bitrate/play count/rating -> canonical
    canon = by_title["midnight city"].canonical()
    assert canon.track_id == 1

    # Redbone: track 6 has Album+Genre+Year filled in, decent bitrate -> canonical
    canon = by_title["redbone"].canonical()
    assert canon.track_id == 6


def test_plan_merges_play_counts_and_max_rating():
    lib = load()
    groups = find_duplicate_groups(lib)
    plan = build_plan(lib, groups)
    by_id = {a.canonical_id: a for a in plan.actions}

    # Midnight City: track1 pc=12 rating=80, track2 pc=3 rating=60 -> merged pc=15, rating=80
    a = by_id[1]
    assert a.merged_play_count == 15
    assert a.merged_rating == 80

    # Blinding Lights: track3 pc=40 rating=100, track4 pc=5 rating=0 -> merged pc=45 rating=100
    a = by_id[3]
    assert a.merged_play_count == 45
    assert a.merged_rating == 100


def test_apply_plan_repoints_all_playlists_and_dedupes_within_playlist():
    lib = load()
    groups = find_duplicate_groups(lib)
    plan = build_plan(lib, groups)
    apply_plan(lib, plan)

    # Duplicate tracks removed, canonical tracks survive.
    assert 2 not in lib.tracks  # Midnight City low-quality copy removed
    assert 1 in lib.tracks
    assert 4 not in lib.tracks  # Blinding Lights feat. variant removed
    assert 3 in lib.tracks
    assert {5, 7} - set(lib.tracks.keys()) == {5, 7}  # Redbone non-canonical removed
    assert 6 in lib.tracks

    # "Home" tracks (not duplicates) both survive untouched.
    assert 8 in lib.tracks and 9 in lib.tracks

    playlists_by_name = {p.name: p for p in lib.playlists}

    # Late Night Drive had [2, 4, 10] -> should become [1, 3, 10]
    assert playlists_by_name["Late Night Drive"].track_ids() == [1, 3, 10]

    # Favorites had [1, 3, 6, 10] -> canonical ids already, unchanged
    assert playlists_by_name["Favorites"].track_ids() == [1, 3, 6, 10]

    # Chill Mix had [8, 9, 5] -> 5 (Redbone dup) becomes 6, others untouched
    assert playlists_by_name["Chill Mix"].track_ids() == [8, 9, 6]

    # Study Focus had [10, 10, 6, 7] -> 7 becomes 6 (collides with existing 6),
    # AND the pre-existing literal duplicate [10, 10] should collapse to one 10.
    assert playlists_by_name["Study Focus"].track_ids() == [10, 6]


def test_metadata_backfill_from_duplicates():
    lib = load()
    groups = find_duplicate_groups(lib)
    plan = build_plan(lib, groups)
    apply_plan(lib, plan)

    # Track 5 (Redbone, no Album) had no album; canonical track 6 already had
    # "Awaken, My Love!" so backfill shouldn't be needed there, but verify
    # canonical's own fields are intact and not blanked.
    canon = lib.tracks[6]
    assert canon.raw.get("Album") == "Awaken, My Love!"
    assert canon.raw.get("Genre") == "Funk"


def test_save_and_reload_roundtrip_preserves_structure():
    lib = load()
    groups = find_duplicate_groups(lib)
    plan = build_plan(lib, groups)
    apply_plan(lib, plan)

    out_path = Path(__file__).parent / "fixtures" / "Library_out.xml"
    lib.save(out_path)

    reloaded = Library.load(out_path)
    assert len(reloaded.tracks) == len(lib.tracks)
    assert len(reloaded.playlists) == len(lib.playlists)
    # Spot check a repointed playlist survived the round trip correctly.
    pl = {p.name: p for p in reloaded.playlists}["Late Night Drive"]
    assert pl.track_ids() == [1, 3, 10]
    out_path.unlink()


def _track(tid, name, artist, total_time_ms=200000, **extra):
    raw = {"Track ID": tid, "Name": name, "Artist": artist, "Total Time": total_time_ms}
    raw.update(extra)
    return Track(track_id=tid, raw=raw)


def test_exact_groups_are_still_tier_exact():
    lib = load()
    groups = find_duplicate_groups(lib)
    assert groups, "fixture should still produce exact groups"
    assert all(g.tier == TIER_EXACT for g in groups)
    assert all(g.similarity == 1.0 for g in groups)


def test_symbol_only_title_is_still_matched_as_a_duplicate():
    """Regression test (v2.0): a title made up entirely of symbols (e.g.
    "$", as in Ty Dolla $ign's song "$") normalizes to an empty string
    (normalize() strips everything but letters/digits/spaces), but that
    doesn't mean the track has no title. find_duplicate_groups() used to
    guard on the *normalized* title being non-empty ("no title at all")
    and silently dropped any such track from grouping entirely -- so two
    real, identically-titled duplicate copies of a symbol-only-titled
    song were never matched by either the exact or the fuzzy pass, and
    survived a "cleaned" library untouched. The guard now checks the raw
    title instead, so two tracks that both legitimately normalize to ""
    still bucket together like any other shared normalized key."""
    tracks = {
        1: _track(1, "$", "Ty Dolla $ign", 193097, Album="Campaign"),
        2: _track(2, "$", "Ty Dolla $ign", 193097, Album="Campaign"),
    }
    lib = Library(raw={"Tracks": {}}, tracks=tracks, playlists=[])
    groups = find_duplicate_groups(lib)
    assert len(groups) == 1
    assert groups[0].tier == TIER_EXACT
    assert {t.track_id for t in groups[0].tracks} == {1, 2}


def test_genuinely_untitled_track_is_still_excluded():
    """A track with no title at all (blank/whitespace-only Name) should
    still be excluded from grouping -- only the normalized-emptiness
    check was wrong, not the underlying intent."""
    tracks = {
        1: _track(1, "", "Some Artist", 200000),
        2: _track(2, "   ", "Some Artist", 200000),
    }
    lib = Library(raw={"Tracks": {}}, tracks=tracks, playlists=[])
    groups = find_duplicate_groups(lib)
    assert groups == []


def test_fuzzy_finds_near_miss_typo_but_not_unrelated_songs():
    tracks = {
        1: _track(1, "Redbone", "Childish Gambino", 326000),
        2: _track(2, "Redbon", "Childish Gambino", 326000),  # typo'd title -> should match
        3: _track(3, "Somebody Else", "The 1975", 300000),   # unrelated -> must not match
    }
    lib = Library(raw={"Tracks": {}}, tracks=tracks, playlists=[])
    fuzzy_groups = find_fuzzy_candidate_groups(lib)
    assert len(fuzzy_groups) == 1
    ids = {t.track_id for t in fuzzy_groups[0].tracks}
    assert ids == {1, 2}
    assert fuzzy_groups[0].tier in (TIER_NEEDS_REVIEW, "high")


def test_low_similarity_is_not_grouped_at_all():
    a = normalize("Redbone")
    b = normalize("Somebody Else")
    assert similarity_score(normalize("Childish Gambino"), a, normalize("The 1975"), b) < 0.80


def test_same_artist_title_with_diverging_duration_is_not_dropped():
    """Regression test (v2.0): same normalized artist+title whose Total
    Time differs by more than DURATION_TOLERANCE_MS used to be split into
    two single-track duration clusters and then silently discarded (a
    singleton cluster is never a group) by find_duplicate_groups(), AND
    skipped by the fuzzy pass (which deliberately ignores exact-key
    pairs) -- so an obvious same-artist/same-title duplicate could vanish
    from detection entirely. This is exactly the real-world case reported
    for e.g. 311's "Amber" appearing on two different releases at two
    different lengths. Such pairs must now be returned, tagged
    tier=duration_mismatch, and never silently lost."""
    tracks = {
        1: _track(1, "Amber", "311", total_time_ms=207072),
        2: _track(2, "Amber", "311", total_time_ms=211173),  # ~4.1s longer
    }
    lib = Library(raw={"Tracks": {}}, tracks=tracks, playlists=[])
    groups = find_duplicate_groups(lib)
    assert len(groups) == 1
    group = groups[0]
    assert group.tier == TIER_DURATION_MISMATCH
    assert {t.track_id for t in group.tracks} == {1, 2}
    assert group.needs_review is True


def test_same_artist_title_within_duration_tolerance_stays_tier_exact():
    """Companion to the regression test above: when durations DO fall
    within DURATION_TOLERANCE_MS, behavior must stay exactly the v1
    tier=exact grouping -- the v2.0 fix only changes what happens to the
    fragments that used to be silently dropped, not the already-working
    case."""
    tracks = {
        1: _track(1, "Same Song", "Some Artist", total_time_ms=200000),
        2: _track(2, "Same Song", "Some Artist", total_time_ms=201500),  # 1.5s, within tolerance
    }
    lib = Library(raw={"Tracks": {}}, tracks=tracks, playlists=[])
    groups = find_duplicate_groups(lib)
    assert len(groups) == 1
    assert groups[0].tier == TIER_EXACT
    assert groups[0].similarity == 1.0


def test_duration_mismatch_group_builds_a_review_only_plan_action():
    """The duration_mismatch tier must flow through build_plan() the same
    way TIER_NEEDS_REVIEW does: built into an action, listed under
    review_actions (never exact_actions), and never pre-selected."""
    tracks = {
        1: _track(1, "Amber", "311", total_time_ms=207072),
        2: _track(2, "Amber", "311", total_time_ms=211173),
    }
    lib = Library(raw={"Tracks": {}}, tracks=tracks, playlists=[])
    groups = find_duplicate_groups(lib)
    plan = build_plan(lib, groups)
    assert len(plan.actions) == 1
    action = plan.actions[0]
    assert action.tier == TIER_DURATION_MISMATCH
    assert action.needs_review is True
    assert action in plan.review_actions
    assert action not in plan.exact_actions


def test_duration_mismatch_does_not_affect_buckets_that_split_cleanly():
    """A bucket with 4 tracks forming two separate same-duration pairs
    (e.g. two distinct duplicate pairs that happen to share a title) must
    still yield two separate tier=exact groups, not one merged
    duration_mismatch group -- the fix only applies when a duration
    cluster would otherwise be a dropped singleton."""
    tracks = {
        1: _track(1, "Same Song", "Artist", total_time_ms=100000),
        2: _track(2, "Same Song", "Artist", total_time_ms=100500),
        3: _track(3, "Same Song", "Artist", total_time_ms=250000),
        4: _track(4, "Same Song", "Artist", total_time_ms=250800),
    }
    lib = Library(raw={"Tracks": {}}, tracks=tracks, playlists=[])
    groups = find_duplicate_groups(lib)
    assert len(groups) == 2
    assert all(g.tier == TIER_EXACT for g in groups)
    ids = sorted(tuple(sorted(t.track_id for t in g.tracks)) for g in groups)
    assert ids == [(1, 2), (3, 4)]


def test_fuzzy_scan_reports_progress_via_callback():
    """v1.7.6: find_fuzzy_candidate_groups' comparison budget is
    time-boxed and reports progress through an optional callback instead
    of a fixed comparisons_budget -- confirm it's actually invoked, with
    a valid 0-1 fraction, and that omitting it entirely still works
    (every existing call site does)."""
    tracks = {
        1: _track(1, "Redbone", "Childish Gambino", 326000),
        2: _track(2, "Redbon", "Childish Gambino", 326000),
    }
    lib = Library(raw={"Tracks": {}}, tracks=tracks, playlists=[])

    calls = []
    groups = find_fuzzy_candidate_groups(
        lib, progress_callback=lambda frac, done, total: calls.append((frac, done, total))
    )
    assert len(groups) == 1
    assert calls, "progress_callback should be invoked at least once"
    assert all(0.0 <= frac <= 1.0 for frac, _done, _total in calls)

    # No callback passed: behavior/return type must be unchanged.
    groups_no_cb = find_fuzzy_candidate_groups(lib)
    assert len(groups_no_cb) == 1


def test_fuzzy_scan_time_budget_of_zero_finds_nothing_and_does_not_raise():
    """An exhausted (zero) time budget should behave like the old
    exhausted comparisons_budget: stop and return what's found so far
    (nothing, here) instead of erroring."""
    tracks = {
        1: _track(1, "Redbone", "Childish Gambino", 326000),
        2: _track(2, "Redbon", "Childish Gambino", 326000),
    }
    lib = Library(raw={"Tracks": {}}, tracks=tracks, playlists=[])
    groups = find_fuzzy_candidate_groups(lib, time_budget_seconds=0.0)
    assert groups == []


def test_exact_matches_excluded_from_fuzzy_pass():
    """Tracks already covered by an exact group shouldn't be re-considered
    by the fuzzy pass (avoids double-counting/duplicate groups)."""
    lib = load()
    exact_groups = find_duplicate_groups(lib)
    exact_ids = {t.track_id for g in exact_groups for t in g.tracks}
    fuzzy_groups = find_fuzzy_candidate_groups(lib, already_grouped_ids=exact_ids)
    fuzzy_ids = {t.track_id for g in fuzzy_groups for t in g.tracks}
    assert fuzzy_ids.isdisjoint(exact_ids)


def test_review_tier_actions_are_not_auto_selected_by_plan_helpers():
    tracks = {
        1: _track(1, "Redbone", "Childish Gambino", 326000, **{"Play Count": 5}),
        2: _track(2, "Redbon", "Childish Gambino", 326000, **{"Play Count": 2}),
    }
    lib = Library(raw={"Tracks": {}, "Playlists": []}, tracks=tracks, playlists=[])
    groups = find_all_candidate_groups(lib)
    plan = build_plan(lib, groups)
    # Whatever tier this near-miss lands in, review_actions must be a subset
    # that never overlaps with exact_actions, and needs_review must be
    # correctly reflected on the action itself.
    review_ids = {a.canonical_id for a in plan.review_actions}
    exact_ids = {a.canonical_id for a in plan.exact_actions}
    assert review_ids.isdisjoint(exact_ids)
    for a in plan.actions:
        assert a.needs_review == (a.tier == TIER_NEEDS_REVIEW)


def test_one_canonical_entry_survives_with_unlimited_playlists():
    """A single physical track (post-merge) must be referenceable from any
    number of playlists, with exactly one Tracks entry remaining."""
    lib = load()
    groups = find_duplicate_groups(lib)
    plan = build_plan(lib, groups)
    apply_plan(lib, plan)

    canonical_id = 3  # Blinding Lights canonical, per existing fixture expectations
    assert canonical_id in lib.tracks
    referencing_playlists = [p for p in lib.playlists if canonical_id in p.track_ids()]
    # However many playlists reference it, there is still exactly one Tracks entry.
    assert len([t for t in lib.tracks if t == canonical_id]) == 1
    assert len(referencing_playlists) >= 1


def test_group_marked_not_duplicate_is_excluded_from_plan():
    lib = load()
    groups = find_duplicate_groups(lib)
    for g in groups:
        g.marked_not_duplicate = True
    plan = build_plan(lib, groups)
    assert plan.actions == []


def test_canonical_override_changes_which_track_is_kept():
    lib = load()
    groups = find_duplicate_groups(lib)
    by_title = {g.key[1]: g for g in groups}
    blinding = by_title["blinding lights"]
    other_id = next(t.track_id for t in blinding.tracks if t.track_id != blinding.canonical().track_id)
    blinding.canonical_override_id = other_id
    assert blinding.canonical().track_id == other_id
    assert "Manually selected" in blinding.canonical_reason()

    plan = build_plan(lib, groups)
    action = next(a for a in plan.actions if a.group_key == blinding.key)
    assert action.canonical_id == other_id
    assert other_id not in action.removed_ids


def test_manual_merge_groups_tracks_the_algorithm_never_grouped():
    lib = load()
    # Tracks 8/9 are both titled "Home" but by two entirely different
    # artists -- find_duplicate_groups must never group these (different
    # songs), confirming this is a genuine "detection found nothing at
    # all" case, not just a re-pick within an existing group.
    exact_groups = find_duplicate_groups(lib)
    for g in exact_groups:
        assert {8, 9} != {t.track_id for t in g.tracks}

    track_a, track_b = lib.tracks[8], lib.tracks[9]
    manual = make_manual_merge_group([track_a, track_b])
    assert manual.tier == TIER_MANUAL
    assert manual.is_manual
    assert not manual.needs_review
    assert {t.track_id for t in manual.tracks} == {8, 9}

    plan = build_plan(lib, exact_groups + [manual])
    action = next(a for a in plan.actions if a.group_key == manual.key)
    assert set(action.removed_ids) | {action.canonical_id} == {8, 9}
    assert action.tier == TIER_MANUAL


def test_manual_merge_key_never_collides_with_real_normalized_key():
    lib = load()
    manual = make_manual_merge_group([lib.tracks[8], lib.tracks[9]])
    real_keys = {g.key for g in find_duplicate_groups(lib)}
    assert manual.key not in real_keys


def test_manual_merge_requires_at_least_two_distinct_tracks():
    lib = load()
    track = lib.tracks[8]
    try:
        make_manual_merge_group([track])
        assert False, "expected ValueError for a single track"
    except ValueError:
        pass
    try:
        make_manual_merge_group([track, track])
        assert False, "expected ValueError for merging a track with itself"
    except ValueError:
        pass


def test_manual_merge_group_can_be_marked_not_duplicate_like_any_other():
    lib = load()
    manual = make_manual_merge_group([lib.tracks[8], lib.tracks[9]])
    manual.marked_not_duplicate = True
    plan = build_plan(lib, [manual])
    assert plan.actions == []


def test_health_report_covers_expected_categories():
    lib = load()
    groups = find_duplicate_groups(lib)
    report = analyze_library(lib, duplicate_groups=groups)
    assert report.total_tracks == len(lib.tracks)
    assert report.duplicate_track_count == sum(len(g.duplicates()) for g in groups)
    assert isinstance(report.estimated_storage_savings_human(), str)
    # Every category is a list of track ids that actually exist in the library.
    for tid in report.missing_artwork:
        assert tid in lib.tracks


def test_health_report_excludes_not_duplicate_groups_from_savings():
    lib = load()
    groups = find_duplicate_groups(lib)
    baseline = analyze_library(lib, duplicate_groups=groups).estimated_duplicate_storage_bytes
    for g in groups:
        g.marked_not_duplicate = True
    after = analyze_library(lib, duplicate_groups=groups).estimated_duplicate_storage_bytes
    assert after == 0
    assert baseline >= after


def test_duration_split_does_not_chain_across_tolerance():
    """Regression test (v1.2.1): tracks must be clustered against a fixed
    anchor duration, not the last-added track in the cluster. A chain of
    pairwise-close durations (0ms, 2900ms, 5800ms) must NOT collapse into
    one cluster just because each consecutive pair is within the 3000ms
    tolerance -- the first and last are 5800ms apart, well over tolerance."""
    from src.core.duplicate_detector import _split_by_duration

    t1 = _track(1, "Same Song", "Artist", total_time_ms=100000)
    t2 = _track(2, "Same Song", "Artist", total_time_ms=102900)
    t3 = _track(3, "Same Song", "Artist", total_time_ms=105800)

    clusters = _split_by_duration([t1, t2, t3])
    cluster_ids = [{t.track_id for t in c} for c in clusters]
    # t1 and t3 (5800ms apart) must never land in the same cluster.
    for ids in cluster_ids:
        assert not ({1, 3} <= ids), f"t1/t3 wrongly chained into one cluster: {cluster_ids}"


def test_merge_action_carries_its_source_group_by_identity():
    """Regression test (v1.2.1): MergeAction.source_group must be the exact
    DuplicateGroup object build_plan() consumed, so UI code (or any caller)
    can resolve "the group behind this action" without relying on row-index
    alignment between plan.actions and a separately-tracked groups list --
    alignment that breaks the moment build_plan() drops a group."""
    lib = load()
    groups = find_duplicate_groups(lib)
    plan = build_plan(lib, groups)
    groups_by_key = {g.key: g for g in groups}
    for action in plan.actions:
        assert action.source_group is not None
        assert action.source_group is groups_by_key[action.group_key]


def test_plan_actions_stay_resolvable_after_a_group_is_dropped():
    """Regression test (v1.2.1): once one group is marked not-duplicate and
    dropped from plan.actions, every remaining action's source_group must
    still point at its own correct group -- not at whatever group happens
    to share the same list index."""
    lib = load()
    groups = find_duplicate_groups(lib)
    assert len(groups) >= 2, "fixture must have at least 2 groups for this test to be meaningful"

    # Mark the first group as not-duplicate, as the UI would after a user
    # clicks "Mark this group as not duplicates" on that row.
    dropped_key = groups[0].key
    groups[0].marked_not_duplicate = True

    plan = build_plan(lib, groups)
    # The dropped group must not appear in the plan at all.
    assert all(a.group_key != dropped_key for a in plan.actions)
    # Every remaining action's source_group must be its own real group,
    # correctly keyed -- never the dropped one, and never mismatched.
    for action in plan.actions:
        assert action.source_group is not None
        assert action.source_group.key == action.group_key
        assert action.source_group.marked_not_duplicate is False


def test_persistent_id_never_backfilled_from_removed_duplicate():
    """Regression test (v1.2.2): a removed duplicate's own 'Persistent ID'
    (Apple's stable per-track identity, used by iTunes/Music.app itself)
    must never be copied onto the surviving canonical track, even if the
    canonical track's own Persistent ID field happens to be empty/missing.
    Backfilling it would make the surviving track wear an identity that
    was never really its own."""
    canon = _track(1, "Song", "Artist", total_time_ms=200000, **{"Play Count": 1})
    dup = _track(
        2, "Song", "Artist", total_time_ms=200000,
        **{"Play Count": 1, "Persistent ID": "DEADBEEF", "Location": "file://localhost/dup.mp3"},
    )
    group = DuplicateGroup(key=("artist", "song"), tracks=[canon, dup])
    lib = Library(raw={"Tracks": {}}, tracks={1: canon, 2: dup}, playlists=[])
    plan = build_plan(lib, [group])
    action = plan.actions[0]
    assert action.canonical_id == 1
    assert "Persistent ID" not in action.backfilled_fields
    assert "Location" in action.backfilled_fields  # ordinary fields still backfill

    apply_plan(lib, plan)
    assert "Persistent ID" not in lib.tracks[1].raw
    assert lib.tracks[1].raw.get("Location") == "file://localhost/dup.mp3"


def test_audit_record_captures_backfill_before_after_and_totals():
    """Regression test (v1.3.0): the audit export must reflect exactly
    what apply_plan() is about to change, read BEFORE mutation. Track 1
    is deliberately made the more "complete" entry (matches Track.
    completeness_score()'s own rules: more filled metadata fields, higher
    bitrate/rating/plays) so it -- not track 2 -- is the one picked as
    canonical, and track 2's extra fields are what get backfilled."""
    from src.core.audit import build_audit_record

    canon = _track(
        1, "Song", "Artist", total_time_ms=200000,
        **{"Play Count": 2, "Rating": 60, "Genre": "Rock", "Bit Rate": 320},
    )
    dup = _track(
        2, "Song", "Artist", total_time_ms=200000,
        **{"Play Count": 5, "Rating": 100, "Album": "Backfilled Album",
           "Location": "file://localhost/dup.mp3"},
    )
    group = DuplicateGroup(key=("artist", "song"), tracks=[canon, dup])
    lib = Library(raw={"Tracks": {}}, tracks={1: canon, 2: dup}, playlists=[])
    plan = build_plan(lib, [group])
    assert plan.actions[0].canonical_id == 1, "test fixture assumption: track 1 must win as canonical"

    record = build_audit_record(lib, plan, app_version="test", output_path=Path("out.xml"))
    assert record.total_groups_merged == 1
    assert record.total_tracks_removed == 1

    change = record.changes[0]
    assert change.canonical_track_id == 1
    assert change.removed_track_ids == [2]
    assert change.play_count_before == 2
    assert change.play_count_after == 7  # 2 + 5, matches apply_plan's sum rule
    assert change.rating_before == 60
    assert change.rating_after == 100  # max(), matches apply_plan's rule

    backfilled = {c.field: c for c in change.backfilled_fields}
    assert "Album" in backfilled
    assert backfilled["Album"].after == "Backfilled Album"
    assert "Location" in backfilled
    # Identity fields must never appear as a backfill, same guarantee as
    # apply_plan()/build_plan()'s _NEVER_BACKFILLED.
    assert "Persistent ID" not in backfilled
    assert "Play Count" not in backfilled
    assert "Rating" not in backfilled

    # The record must still be accurate even applied afterward -- i.e.
    # building the audit record must not itself have mutated anything.
    apply_plan(lib, plan)
    assert lib.tracks[1].raw.get("Play Count") == 7
    assert lib.tracks[1].raw.get("Album") == "Backfilled Album"


def test_audit_record_serializes_to_json_round_trip(tmp_path=None):
    import json
    import tempfile
    from src.core.audit import build_audit_record

    canon = _track(1, "Song", "Artist", **{"Play Count": 0, "Genre": "Rock", "Bit Rate": 320})
    dup = _track(2, "Song", "Artist", **{"Play Count": 3})
    group = DuplicateGroup(key=("artist", "song"), tracks=[canon, dup])
    lib = Library(raw={"Tracks": {}}, tracks={1: canon, 2: dup}, playlists=[])
    plan = build_plan(lib, [group])
    assert plan.actions[0].canonical_id == 1, "test fixture assumption: track 1 must win as canonical"
    record = build_audit_record(lib, plan, app_version="test", output_path=Path("out.xml"))

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "audit.json"
        record.save(out)
        assert out.exists()
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["total_groups_merged"] == 1
        assert loaded["changes"][0]["canonical_track_id"] == 1
        assert loaded["changes"][0]["removed_track_ids"] == [2]


def test_artwork_file_uri_to_path_handles_local_and_remote():
    from src.core.artwork import file_uri_to_path

    local = file_uri_to_path("file://localhost/Users/me/Music/song.mp3")
    assert local is not None
    assert str(local).endswith("song.mp3")

    assert file_uri_to_path("") is None
    assert file_uri_to_path("https://example.com/stream.mp3") is None


def test_artwork_read_embedded_artwork_missing_file_returns_none():
    from src.core.artwork import read_embedded_artwork

    assert read_embedded_artwork(Path("/nonexistent/path/does_not_exist.mp3")) is None


def test_artwork_read_embedded_artwork_id3_apic_round_trip():
    """Builds a minimal but real ID3v2.3 tag with an APIC frame and
    confirms the hand-rolled parser extracts the same image bytes back
    out, without needing a real MP3 file or a tagging dependency."""
    import struct
    import tempfile
    from src.core.artwork import read_embedded_artwork

    image_bytes = b"\xff\xd8\xff\xe0FAKEJPEGDATA"  # JPEG-ish magic, arbitrary payload
    mime = b"image/jpeg\x00"
    picture_type = b"\x03"  # front cover
    description = b"\x00"  # empty, UTF-8 terminator
    apic_payload = b"\x00" + mime + picture_type + description + image_bytes

    frame_header = b"APIC" + struct.pack(">I", len(apic_payload)) + b"\x00\x00"
    frame = frame_header + apic_payload

    tag_size = len(frame)

    def syncsafe(n):
        return bytes(((n >> (7 * i)) & 0x7F) for i in (3, 2, 1, 0))

    id3_header = b"ID3" + bytes([3, 0]) + b"\x00" + syncsafe(tag_size)

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "track.mp3"
        path.write_bytes(id3_header + frame + b"\x00" * 50)  # + trailing audio-ish padding
        result = read_embedded_artwork(path)
        assert result == image_bytes


def test_artwork_read_embedded_artwork_flac_picture_round_trip():
    """Builds a minimal but real FLAC file (fLaC marker + a METADATA_BLOCK_
    PICTURE block) and confirms the hand-rolled parser extracts the same
    image bytes back out, without needing a real FLAC file or a tagging
    dependency (v1.7.6: FLAC/ALAC embedded-artwork support)."""
    import struct
    import tempfile
    from src.core.artwork import read_embedded_artwork

    image_bytes = b"\x89PNGFAKEPNGDATA"
    mime = b"image/png"
    description = b""
    picture_payload = struct.pack(">I", 3)  # picture_type: front cover
    picture_payload += struct.pack(">I", len(mime)) + mime
    picture_payload += struct.pack(">I", len(description)) + description
    picture_payload += struct.pack(">IIII", 10, 10, 24, 0)  # width/height/depth/colors
    picture_payload += struct.pack(">I", len(image_bytes)) + image_bytes

    # Last-metadata-block flag set (0x80) + block type 6 (PICTURE) in the
    # first byte, 24-bit big-endian block length in the next three.
    block_header = bytes([0x80 | 6]) + struct.pack(">I", len(picture_payload))[1:]

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "track.flac"
        path.write_bytes(b"fLaC" + block_header + picture_payload + b"\x00" * 50)
        result = read_embedded_artwork(path)
        assert result == image_bytes


def test_artwork_read_embedded_artwork_flac_no_picture_block_returns_none():
    """A FLAC file whose only metadata block is STREAMINFO (no PICTURE
    block) should report "no artwork", not raise or misparse."""
    import struct
    import tempfile
    from src.core.artwork import read_embedded_artwork

    streaminfo_body = b"\x00" * 34
    block_header = bytes([0x80 | 0]) + struct.pack(">I", len(streaminfo_body))[1:]

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "track.flac"
        path.write_bytes(b"fLaC" + block_header + streaminfo_body)
        assert read_embedded_artwork(path) is None


def test_artwork_file_uri_to_path_handles_windows_drive_letter():
    """Bug fix: 'file://localhost/C:/Users/.../song.mp3' (the shape iTunes
    writes on Windows) previously round-tripped to a Path with a leading
    slash still in front of the drive letter, which never resolves to a
    real file on Windows -- see core/artwork.py's file_uri_to_path
    docstring."""
    from src.core.artwork import file_uri_to_path

    p = file_uri_to_path("file://localhost/C:/Users/me/Music/song.mp3")
    assert p is not None
    assert str(p) in ("C:/Users/me/Music/song.mp3", "C:\\Users\\me\\Music\\song.mp3")
    assert not str(p).startswith("/C:")

    # Still handles a plain POSIX-style location with no drive letter.
    p2 = file_uri_to_path("file://localhost/Users/me/Music/song.mp3")
    assert str(p2).endswith("song.mp3")
    assert not str(p2).startswith("//")


def _album_track(track_id, artist, album, name, bitrate, album_artist=None):
    raw = {
        "Track ID": track_id,
        "Name": name,
        "Artist": artist,
        "Album": album,
        "Bit Rate": bitrate,
    }
    if album_artist:
        raw["Album Artist"] = album_artist
    return Track(track_id=track_id, raw=raw)


def test_find_album_duplicate_groups_flags_whole_album_reimport():
    from src.core.duplicate_detector import find_album_duplicate_groups

    tracks = {}
    # Original album at 128kbps: 4 tracks.
    for i, title in enumerate(["Track One", "Track Two", "Track Three", "Track Four"], start=1):
        t = _album_track(i, "The Band", "Greatest Album", title, 128)
        tracks[t.track_id] = t
    # Same album re-imported at 320kbps: same 4 tracks.
    for i, title in enumerate(["Track One", "Track Two", "Track Three", "Track Four"], start=101):
        t = _album_track(i, "The Band", "Greatest Album", title, 320)
        tracks[t.track_id] = t

    lib = Library(raw={}, tracks=tracks, playlists=[])
    groups = find_album_duplicate_groups(lib)

    assert len(groups) == 1
    group = groups[0]
    assert group.album == "Greatest Album"
    assert group.bitrates == [128, 320]
    assert len(group.duplicated_track_titles) == 4
    assert group.duplicate_track_count == 4  # one removable copy per track


def test_find_album_duplicate_groups_ignores_small_overlap():
    """A couple of shared titles across two different albums (e.g. a
    Greatest Hits compilation sharing a song with a studio album) should
    NOT be flagged as a whole-album reimport -- that's what the ordinary
    per-track matcher already covers."""
    from src.core.duplicate_detector import find_album_duplicate_groups

    tracks = {}
    t1 = _album_track(1, "The Band", "Studio Album", "Hit Song", 128)
    t2 = _album_track(2, "The Band", "Studio Album", "Hit Song", 320)
    tracks[t1.track_id] = t1
    tracks[t2.track_id] = t2

    lib = Library(raw={}, tracks=tracks, playlists=[])
    groups = find_album_duplicate_groups(lib)
    assert groups == []


def test_find_album_duplicate_groups_ignores_single_bitrate_album():
    from src.core.duplicate_detector import find_album_duplicate_groups

    tracks = {}
    for i, title in enumerate(["A", "B", "C"], start=1):
        t = _album_track(i, "Solo Artist", "One Copy Album", title, 256)
        tracks[t.track_id] = t

    lib = Library(raw={}, tracks=tracks, playlists=[])
    assert find_album_duplicate_groups(lib) == []


def test_library_lock_blocks_second_acquire_same_file(tmp_path=None):
    import tempfile
    from src.core.library_lock import LibraryAlreadyOpenError, LibraryLock

    with tempfile.TemporaryDirectory() as d:
        lock_dir = Path(d) / "locks"
        library_path = Path(d) / "Library.xml"
        library_path.write_text("<plist></plist>")

        lock_a = LibraryLock(lock_dir, library_path)
        lock_a.acquire()
        try:
            lock_b = LibraryLock(lock_dir, library_path)
            raised = False
            try:
                lock_b.acquire()
            except LibraryAlreadyOpenError:
                raised = True
            assert raised, "second lock on the same library should be refused"
        finally:
            lock_a.release()

        # Once released, a new lock attempt succeeds.
        lock_c = LibraryLock(lock_dir, library_path)
        lock_c.acquire()
        lock_c.release()


def test_library_lock_allows_different_files_concurrently():
    import tempfile
    from src.core.library_lock import LibraryLock

    with tempfile.TemporaryDirectory() as d:
        lock_dir = Path(d) / "locks"
        path_a = Path(d) / "LibraryA.xml"
        path_b = Path(d) / "LibraryB.xml"
        path_a.write_text("<plist></plist>")
        path_b.write_text("<plist></plist>")

        lock_a = LibraryLock(lock_dir, path_a)
        lock_b = LibraryLock(lock_dir, path_b)
        lock_a.acquire()
        lock_b.acquire()  # different file -- must not raise
        lock_a.release()
        lock_b.release()


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError:
            print(f"FAIL  {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
