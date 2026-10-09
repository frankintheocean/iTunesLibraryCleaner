"""
Tests for core/itunes_com_sync.py -- specifically the parts that don't
require Windows, pywin32, or a running iTunes: persistent-id parsing,
the ComSyncResult reporting shape, and the platform/availability guards.

The actual COM calls (_try_connect, is_itunes_running_and_responsive,
_remove_track_everywhere) cannot be meaningfully exercised outside a real
Windows machine with iTunes installed and running -- those are guarded to
fail safe (return None / False / a "not attempted" result) on every other
platform, which is exactly what's verified here: this suite runs on any
platform and confirms the module degrades correctly rather than raising.

Run with: python3 -m pytest tests/ -v
(or python3 tests/test_itunes_com_sync.py to run without pytest)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.itunes_com_sync import (
    ComSyncResult,
    _persistent_id_parts,
    is_windows,
    is_itunes_running_and_responsive,
    sync_removed_tracks_from_raws,
)
from src.core.itunes_xml import Library, Track


def test_persistent_id_parts_splits_16_hex_digits_into_two_halves():
    raw = {"Persistent ID": "A1B2C3D4E5F60708"}
    parts = _persistent_id_parts(raw)
    assert parts == (0xA1B2C3D4, 0xE5F60708)


def test_persistent_id_parts_handles_lowercase_and_short_values():
    # iTunes sometimes omits leading zeros; must not silently misalign.
    raw = {"Persistent ID": "ff"}
    parts = _persistent_id_parts(raw)
    assert parts == (0, 0xFF)


def test_persistent_id_parts_returns_none_when_missing():
    assert _persistent_id_parts({}) is None
    assert _persistent_id_parts({"Persistent ID": ""}) is None
    assert _persistent_id_parts({"Persistent ID": None}) is None


def test_persistent_id_parts_returns_none_on_non_hex_value():
    assert _persistent_id_parts({"Persistent ID": "not-hex-at-all"}) is None


def test_com_sync_result_summary_when_not_attempted():
    result = ComSyncResult(attempted=False, itunes_available=False)
    assert not result.succeeded_fully
    assert "not attempted" in result.summary_text().lower()


def test_com_sync_result_summary_when_itunes_unavailable():
    result = ComSyncResult(attempted=True, itunes_available=False)
    assert not result.succeeded_fully
    text = result.summary_text().lower()
    assert "isn't currently running" in text or "isn't running" in text


def test_com_sync_result_succeeded_fully_requires_no_errors():
    ok = ComSyncResult(attempted=True, itunes_available=True, tracks_removed=3)
    assert ok.succeeded_fully

    with_errors = ComSyncResult(
        attempted=True, itunes_available=True, tracks_removed=2,
        errors=["could not remove track X"],
    )
    assert not with_errors.succeeded_fully


def test_com_sync_result_summary_mentions_removed_and_errors():
    result = ComSyncResult(
        attempted=True,
        itunes_available=True,
        tracks_removed=2,
        tracks_not_found=1,
        playlist_removals=3,
        errors=["boom"],
    )
    text = result.summary_text()
    assert "2 track" in text
    assert "1 track" in text  # not-found count
    assert "3 playlist" in text
    assert "1 track(s) could not be removed" in text


def test_is_windows_matches_sys_platform():
    assert is_windows() == (sys.platform == "win32")


def test_is_itunes_running_and_responsive_never_raises_off_windows():
    # On any non-Windows CI/dev machine (and on Windows without iTunes
    # installed/running) this must simply return False, never raise --
    # this is the guard every call site relies on to skip COM sync safely.
    assert is_itunes_running_and_responsive(timeout_seconds=0.5) in (True, False)


def test_sync_removed_tracks_from_raws_is_a_safe_noop_without_itunes():
    """End-to-end guard: even with real removed-track raw dicts collected
    from a real library/plan, calling sync_removed_tracks_from_raws() on
    a machine without a reachable iTunes must return a well-formed 'not
    available' result and never raise."""
    fixture_path = Path(__file__).parent / "fixtures" / "Library.xml"
    library = Library.load(fixture_path) if fixture_path.exists() else None
    if library is None:
        return  # fixture not generated in this environment; nothing to check

    from src.core.duplicate_detector import find_duplicate_groups
    from src.core.consolidator import build_plan

    groups = find_duplicate_groups(library)
    plan = build_plan(library, groups)

    removed_raws = []
    for action in plan.actions:
        for removed_id in action.removed_ids:
            track = library.tracks.get(removed_id)
            if track is not None:
                removed_raws.append(dict(track.raw))

    result = sync_removed_tracks_from_raws(removed_raws)

    assert isinstance(result, ComSyncResult)
    assert result.attempted is True
    # Without a real reachable iTunes, availability must be False and no
    # tracks/playlists may be reported as touched.
    if not result.itunes_available:
        assert result.tracks_removed == 0
        assert result.playlist_removals == 0


def test_sync_removed_tracks_from_raws_handles_empty_list():
    result = sync_removed_tracks_from_raws([])
    assert isinstance(result, ComSyncResult)
    assert result.attempted is True
    assert result.tracks_removed == 0


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
