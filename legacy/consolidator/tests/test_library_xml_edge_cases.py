"""
Edge-case coverage for the Library.xml parser (src/core/itunes_xml.py,
src/core/plist_stream.py) beyond the single synthetic fixture used by
test_consolidation.py. Three areas:

1. Malformed/truncated input (tests/fixtures/malformed/) -- a real
   Library.xml can arrive incomplete (interrupted export/copy/sync) or
   damaged (hand-edited, disk corruption); the app must fail with a
   clear LibraryParseError pointing at the file, never a raw traceback
   or, worse, a silent partial load.
2. Non-ASCII tags (tests/fixtures/Library_unicode_folders.xml) -- CJK,
   accented Latin, and emoji in track/playlist names must round-trip
   exactly through parse -> save -> parse, and duplicate-detection
   normalization must handle them without crashing.
3. Playlist folders (same fixture) -- iTunes/Music represents a playlist
   folder as a playlist entry with a "Folder" key; children reference it
   via "Parent Persistent ID" rather than true XML nesting. The app must
   read every playlist (folder and child alike) without special-casing
   folders as anything other than an ordinary, non-special playlist.

Run with: python3 -m pytest tests/test_library_xml_edge_cases.py -v
(or python3 tests/test_library_xml_edge_cases.py to run without pytest)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.itunes_xml import Library, LibraryParseError
from src.core.duplicate_detector import find_duplicate_groups, normalize

FIXTURES = Path(__file__).parent / "fixtures"
MALFORMED = FIXTURES / "malformed"
UNICODE_FIXTURE = FIXTURES / "Library_unicode_folders.xml"


def _assert_parse_error(path: Path):
    assert path.exists(), f"missing fixture: {path}"
    try:
        Library.load(path)
    except LibraryParseError as exc:
        # Must name the offending file, not just describe the failure in
        # the abstract -- this is what lets the app's error dialog tell
        # the user which file is the problem.
        assert path.name in str(exc), (
            f"LibraryParseError message should mention {path.name!r}: {exc}"
        )
        return
    raise AssertionError(f"expected LibraryParseError loading {path.name}, got no exception")


# --- Malformed / truncated -------------------------------------------

def test_truncated_xml_raises_library_parse_error():
    _assert_parse_error(MALFORMED / "truncated.xml")


def test_mismatched_tags_raises_library_parse_error():
    _assert_parse_error(MALFORMED / "mismatched_tags.xml")


def test_empty_file_raises_library_parse_error():
    _assert_parse_error(MALFORMED / "empty.xml")


def test_missing_tracks_key_raises_library_parse_error_with_guidance():
    # This one is well-formed XML/plist -- it fails Library.load's own
    # "does this look like an iTunes export" check, not the XML parser,
    # so it goes through a different raise site (see itunes_xml.Library.load)
    # and should mention how to produce a valid export.
    path = MALFORMED / "missing_tracks_key.xml"
    try:
        Library.load(path)
    except LibraryParseError as exc:
        msg = str(exc)
        assert path.name in msg
        assert "Tracks" in msg
        return
    raise AssertionError("expected LibraryParseError for a plist missing the Tracks key")


def test_entity_declaration_is_rejected_not_expanded():
    # XXE guard: StreamingTracksParser._handle_entity_decl must reject
    # any file declaring an XML entity outright, rather than expanding
    # it into track data. A regression here would be a real security
    # issue (arbitrary local file read via an external entity), not
    # just a parsing bug, so this fixture uses only a benign internal
    # entity -- the guard fires on the declaration itself, before it
    # matters whether the entity is internal or external.
    path = MALFORMED / "entity_declaration.xml"
    try:
        Library.load(path)
    except LibraryParseError as exc:
        assert "entity" in str(exc).lower()
        return
    raise AssertionError("expected LibraryParseError rejecting the entity declaration")


def test_truncated_xml_does_not_partially_populate_tracks():
    # Guard against a regression where a future refactor might catch the
    # parse error but still hand back a Library with whatever tracks had
    # streamed in before the truncation -- silent partial data is worse
    # than a clean failure here, since consolidation could then run
    # against an incomplete picture of the library without any warning.
    try:
        Library.load(MALFORMED / "truncated.xml")
        raise AssertionError("expected LibraryParseError")
    except LibraryParseError:
        pass  # Library.load raised before returning anything -- nothing to inspect.


# --- Non-ASCII tags -----------------------------------------------------

def _load_unicode_fixture() -> Library:
    assert UNICODE_FIXTURE.exists(), "Run tests/generate_fixture.py first"
    return Library.load(UNICODE_FIXTURE)


def test_non_ascii_track_names_round_trip_exactly():
    lib = _load_unicode_fixture()
    t1 = lib.tracks[1]
    assert t1.name == "日本の歌 \U0001F3B5"
    assert t1.artist == "Café Müller"
    assert t1.album == "作品集"

    t3 = lib.tracks[3]
    assert t3.name == "Naïve"
    assert t3.artist == "Zażółć Gęślą Jaźń"
    assert t3.album == "Über Album"


def test_non_ascii_names_survive_save_and_reload(tmp_path_factory=None):
    import tempfile

    lib = _load_unicode_fixture()
    out = Path(tempfile.mktemp(suffix=".xml"))
    lib.save(out)
    reloaded = Library.load(out)

    assert reloaded.tracks[1].name == lib.tracks[1].name
    assert reloaded.tracks[1].artist == lib.tracks[1].artist
    assert reloaded.tracks[3].artist == lib.tracks[3].artist

    playlist_names = {p.name for p in lib.playlists}
    reloaded_names = {p.name for p in reloaded.playlists}
    assert playlist_names == reloaded_names


def test_normalize_handles_non_ascii_without_crashing():
    # NFKD + combining-mark stripping folds accented Latin to its
    # unaccented ASCII form, so accent-only differences still match.
    assert normalize("Café Müller") == normalize("Cafe Muller")
    # _NON_ALNUM (src/core/duplicate_detector.py) is deliberately
    # ASCII-only ([^a-z0-9 ]+), so non-Latin scripts and symbols/emoji
    # are stripped out entirely rather than preserved -- documented here
    # as current, existing behavior (two different CJK titles both
    # normalize to "", so they'd collide as an exact-tier match on title
    # alone). Not this test's concern to relitigate; what matters here is
    # that normalize() never raises on this input.
    assert normalize("日本の歌") == ""
    assert normalize("\U0001F3B5\U0001F3B6\U0001F4C1") == ""
    # Must not raise for any of these -- the real risk here is an
    # unhandled exception from a regex/case-folding step assuming ASCII.
    normalize("Zażółć Gęślą Jaźń")


def test_duplicate_detection_runs_cleanly_on_non_ascii_library():
    # Not asserting a specific grouping outcome (the fixture's "(Live)"
    # variant is a deliberate near-miss, not a guaranteed fuzzy match at
    # default thresholds) -- the point of this test is that scanning a
    # library full of non-ASCII tags completes without raising.
    lib = _load_unicode_fixture()
    groups = find_duplicate_groups(lib)
    assert isinstance(groups, list)


# --- Playlist folders -----------------------------------------------------

def test_all_playlists_including_folders_are_loaded():
    lib = _load_unicode_fixture()
    names = {p.name for p in lib.playlists}
    assert "\U0001F4C1 Road Trips" in names       # top-level folder
    assert "Nested Folder \U0001F4C1" in names    # folder nested inside a folder
    assert "夏 2024" in names                      # child of the top-level folder
    assert "Café Sessions" in names               # child of the nested folder
    assert "Favorites \u2764\ufe0f" in names       # ordinary playlist, for contrast


def test_folder_playlists_are_not_treated_as_special():
    # is_special is reserved for iTunes' own built-ins (Library, Music,
    # smart playlists, etc.) -- a user-created folder is none of those
    # and must flow through consolidation like any other user playlist,
    # not be silently skipped.
    lib = _load_unicode_fixture()
    by_name = {p.name: p for p in lib.playlists}

    folder = by_name["\U0001F4C1 Road Trips"]
    assert folder.is_special is False
    assert folder.is_smart is False

    nested_folder = by_name["Nested Folder \U0001F4C1"]
    assert nested_folder.is_special is False


def test_folder_entry_has_no_track_items_children_do():
    lib = _load_unicode_fixture()
    by_name = {p.name: p for p in lib.playlists}

    # The folder entries themselves carry no "Playlist Items" (real
    # iTunes exports don't give folders track lists) -- track_ids() must
    # degrade to an empty list rather than raising a KeyError.
    assert by_name["\U0001F4C1 Road Trips"].track_ids() == []
    assert by_name["Nested Folder \U0001F4C1"].track_ids() == []

    # Children under each folder level do carry their own track lists.
    assert by_name["夏 2024"].track_ids() == [1, 3]
    assert by_name["Café Sessions"].track_ids() == [2]


def test_nested_folder_child_survives_save_and_reload():
    import tempfile

    lib = _load_unicode_fixture()
    out = Path(tempfile.mktemp(suffix=".xml"))
    lib.save(out)
    reloaded = Library.load(out)

    reloaded_by_name = {p.name: p for p in reloaded.playlists}
    assert reloaded_by_name["Café Sessions"].track_ids() == [2]
    assert reloaded_by_name["Nested Folder \U0001F4C1"].is_special is False


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
