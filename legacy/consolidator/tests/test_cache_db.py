"""
Run with: python3 -m pytest tests/ -v
"""

import datetime
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.cache_db import CacheDB


def _make_db(tmp_path) -> CacheDB:
    return CacheDB(Path(tmp_path) / "cache.sqlite3")


def test_snapshot_roundtrip_preserves_naive_datetime_exactly():
    """Regression test (v1.3.14-pre): a library freshly loaded via
    Library.load()/plist_stream.py always has naive datetimes for plist
    <date> fields (matching real plistlib.load() behavior -- verified
    directly against the stdlib, not assumed). A snapshot save/restore
    round-trip must reproduce that exact same naive value -- not
    silently promote it to a timezone-aware datetime, which previously
    happened here and could later crash core/consolidator.py's
    min(dates) call if a restored track were ever compared against a
    freshly-loaded (naive) one.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp)
        try:
            naive_date = datetime.datetime(2020, 1, 1, 0, 0, 0)
            raw = {"Tracks": {"1": {"Track ID": 1, "Date Added": naive_date}}}

            snap_id = db.save_snapshot(raw, "Library.xml", label="test")
            restored = db.load_snapshot(snap_id)
            restored_date = restored["Tracks"]["1"]["Date Added"]

            assert restored_date == naive_date
            assert restored_date.tzinfo is None, (
                "restored 'Date Added' must stay naive, matching what "
                "plistlib/plist_stream.py actually produce for a freshly "
                "loaded library -- an aware datetime here is a regression"
            )
        finally:
            db.close()


def test_snapshot_roundtrip_preserves_aware_datetime_if_ever_given():
    """Not the shape this app currently produces, but the round-trip
    should be faithful either way: an aware datetime that was actually
    stored should come back aware with the same offset, not silently
    stripped or altered."""
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp)
        try:
            aware_date = datetime.datetime(2020, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
            raw = {"Tracks": {"1": {"Track ID": 1, "Date Added": aware_date}}}

            snap_id = db.save_snapshot(raw, "Library.xml", label="test")
            restored = db.load_snapshot(snap_id)
            restored_date = restored["Tracks"]["1"]["Date Added"]

            assert restored_date == aware_date
            assert restored_date.tzinfo is not None
        finally:
            db.close()


def test_ui_setting_roundtrip_and_default_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp)
        try:
            assert db.get_setting("nonexistent", default="fallback") == "fallback"
            db.set_setting("theme_preference", "dark")
            assert db.get_setting("theme_preference") == "dark"
            db.set_setting("theme_preference", "light")
            assert db.get_setting("theme_preference") == "light"
        finally:
            db.close()


if __name__ == "__main__":
    test_snapshot_roundtrip_preserves_naive_datetime_exactly()
    test_snapshot_roundtrip_preserves_aware_datetime_if_ever_given()
    test_ui_setting_roundtrip_and_default_fallback()
    print("All tests passed!")
