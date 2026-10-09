"""
Builds a synthetic iTunes Library.xml with the real Apple plist schema:
several duplicate groups (exact dupes, feat./remaster tag variants, and
one same-title-different-song trap), plus playlists referencing various
combinations of the duplicates, ratings, and play counts -- so
consolidation logic is exercised against realistic structure.

NOT real user data. Used only to verify the parser/consolidator work
correctly, since no populated library was available.
"""

import plistlib
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).parent / "fixtures" / "Library.xml"

# Additional edge-case fixtures (see test_library_xml_edge_cases.py):
# non-ASCII tags + playlist-folder nesting is built here since it's a
# valid plist (plistlib can write it); malformed/truncated XML fixtures
# are deliberately broken and are written as static files instead (see
# tests/fixtures/malformed/), since there's no valid structure for a
# generator function to produce here.
OUT_UNICODE_FOLDERS = Path(__file__).parent / "fixtures" / "Library_unicode_folders.xml"


def track(tid, name, artist, album, ms, bitrate=256, play_count=0, rating=0,
          date_added="2020-01-01T00:00:00Z", extra=None):
    d = {
        "Track ID": tid,
        "Name": name,
        "Artist": artist,
        "Album": album,
        "Total Time": ms,
        "Bit Rate": bitrate,
        "Play Count": play_count,
        "Rating": rating,
        "Date Added": datetime.fromisoformat(date_added.replace("Z", "+00:00")),
        "Location": f"file://localhost/Users/test/Music/{artist}/{album}/{name}.m4a",
        "Kind": "AAC audio file",
        "Track Type": "File",
    }
    if extra:
        d.update(extra)
    return d


def playlist(name, pid, track_ids, special_key=None):
    d = {"Name": name, "Playlist ID": pid, "Playlist Items": [{"Track ID": t} for t in track_ids]}
    if special_key:
        d[special_key] = True
    return d


def build():
    tracks = {}

    # --- Duplicate group 1: exact duplicate (same everything, imported twice)
    tracks[1] = track(1, "Midnight City", "M83", "Hurry Up, We're Dreaming", 243000,
                       bitrate=256, play_count=12, rating=80,
                       date_added="2019-03-01T00:00:00Z")
    tracks[2] = track(2, "Midnight City", "M83", "Hurry Up, We're Dreaming", 243000,
                       bitrate=128, play_count=3, rating=60,
                       date_added="2021-07-15T00:00:00Z")

    # --- Duplicate group 2: "feat." tag variant + remaster tag variant
    tracks[3] = track(3, "Blinding Lights", "The Weeknd", "After Hours", 200000,
                       bitrate=320, play_count=40, rating=100,
                       date_added="2020-01-01T00:00:00Z",
                       extra={"Artwork Count": 1})
    tracks[4] = track(4, "Blinding Lights (feat. Rosalia)", "The Weeknd", "After Hours (Remix)",
                       201500, bitrate=192, play_count=5, rating=0,
                       date_added="2020-06-01T00:00:00Z")

    # --- Duplicate group 3: three copies, varying metadata completeness
    tracks[5] = track(5, "Redbone", "Childish Gambino", "", 326000, bitrate=192, play_count=1,
                       rating=0, date_added="2022-01-01T00:00:00Z")
    tracks[6] = track(6, "Redbone", "Childish Gambino", "Awaken, My Love!", 326000, bitrate=256,
                       play_count=8, rating=90, date_added="2018-11-11T00:00:00Z",
                       extra={"Genre": "Funk", "Year": 2016})
    tracks[7] = track(7, "Redbone", "Childish Gambino", "Awaken, My Love!", 327200, bitrate=320,
                       play_count=2, rating=0, date_added="2023-02-02T00:00:00Z")

    # --- NOT a duplicate: same title, different artist/song (must not merge)
    tracks[8] = track(8, "Home", "Edward Sharpe & The Magnetic Zeros", "Up From Below", 302000,
                       play_count=6, rating=0, date_added="2017-05-05T00:00:00Z")
    tracks[9] = track(9, "Home", "Gabrielle Aplin", "English Rain", 222000,
                       play_count=1, rating=0, date_added="2019-09-09T00:00:00Z")

    # --- Unique track, no duplicates
    tracks[10] = track(10, "Weird Fishes/Arpeggi", "Radiohead", "In Rainbows", 305000,
                        play_count=20, rating=100, date_added="2015-01-01T00:00:00Z")

    playlists = [
        playlist("Library", 100, list(tracks.keys()), special_key="Master"),
        playlist("Music", 101, list(tracks.keys()), special_key="Music"),
        # User playlist referencing the LOW-quality copy of Midnight City (id 2)
        # and the low-quality Blinding Lights variant (id 4) -- must be
        # repointed to the canonical (1) and (3) after consolidation.
        playlist("Late Night Drive", 200, [2, 4, 10]),
        # User playlist referencing the canonical copies directly already.
        playlist("Favorites", 201, [1, 3, 6, 10]),
        # User playlist referencing BOTH the "Home" tracks (different songs,
        # must remain two separate entries, never merged).
        playlist("Chill Mix", 202, [8, 9, 5]),
        # Playlist with a duplicate reference to the SAME track twice
        # (edge case: should be de-duplicated on repoint, not just left as-is
        # if it becomes a repoint collision). Also references two members of
        # duplicate group 3 (6 and 7) which should collapse to one reference
        # to the canonical after merge.
        playlist("Study Focus", 203, [10, 10, 6, 7]),
    ]

    root = {
        "Major Version": 1,
        "Minor Version": 1,
        "Application Version": "12.13.6.3",
        "Date": datetime.now(timezone.utc),
        "Music Folder": "file://localhost/Users/test/Music/",
        "Library Persistent ID": "SYNTHETICTESTLIB01",
        "Tracks": {str(k): v for k, v in tracks.items()},
        "Playlists": playlists,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "wb") as f:
        plistlib.dump(root, f, fmt=plistlib.FMT_XML)
    print(f"Wrote synthetic fixture: {OUT} ({len(tracks)} tracks, {len(playlists)} playlists)")


def build_unicode_folders():
    """Second fixture covering two things the main fixture above doesn't:

    1. Non-ASCII tags -- CJK, accented Latin, and emoji in track and
       playlist names -- to verify the parser round-trips them exactly
       (no mangling/mojibake) and that duplicate-detection normalization
       (accent stripping, case folding) behaves sanely against them.
    2. Playlist folders: real iTunes/Music exports represent a playlist
       folder as a playlist entry with a "Folder" key, and its children
       as ordinary playlist entries carrying a "Parent Persistent ID"
       pointing at the folder's own "Playlist Persistent ID" -- there is
       no nested/tree XML structure. Includes a folder nested inside
       another folder (two levels) since that's valid in real libraries.
    """
    tracks = {
        1: track(1, "日本の歌 \U0001F3B5", "Café Müller", "作品集", 200000,
                  play_count=5, rating=80, date_added="2021-01-01T00:00:00Z"),
        # Deliberate near-duplicate of track 1 differing only by accent
        # (é -> e) and an added "(Live)" tag, to check that NFKD/accent
        # normalization treats them as comparable rather than crashing
        # or silently mis-comparing on non-ASCII input.
        2: track(2, "日本の歌 \U0001F3B5 (Live)", "Cafe Muller", "作品集", 205000,
                  play_count=1, rating=0, date_added="2022-06-01T00:00:00Z"),
        3: track(3, "Naïve", "Zażółć Gęślą Jaźń", "Über Album", 180000,
                  play_count=2, rating=60, date_added="2020-03-03T00:00:00Z"),
    }

    playlists = [
        playlist("Library", 100, list(tracks.keys()), special_key="Master"),
        playlist("Music", 101, list(tracks.keys()), special_key="Music"),
        # Top-level folder containing one playlist and one sub-folder.
        {"Name": "\U0001F4C1 Road Trips", "Playlist ID": 200,
         "Playlist Persistent ID": "FOLDERROOT01", "Folder": True},
        {"Name": "夏 2024", "Playlist ID": 201,
         "Parent Persistent ID": "FOLDERROOT01",
         "Playlist Items": [{"Track ID": 1}, {"Track ID": 3}]},
        {"Name": "Nested Folder \U0001F4C1", "Playlist ID": 202,
         "Playlist Persistent ID": "FOLDERNEST01",
         "Parent Persistent ID": "FOLDERROOT01", "Folder": True},
        {"Name": "Café Sessions", "Playlist ID": 203,
         "Parent Persistent ID": "FOLDERNEST01",
         "Playlist Items": [{"Track ID": 2}]},
        # Ordinary (non-folder) playlist for comparison/baseline.
        playlist("Favorites \u2764\ufe0f", 300, [1, 2, 3]),
    ]

    root = {
        "Major Version": 1,
        "Minor Version": 1,
        "Application Version": "12.13.6.3",
        "Date": datetime.now(timezone.utc),
        "Music Folder": "file://localhost/Users/test/Music/",
        "Library Persistent ID": "SYNTHETICTESTLIB02",
        "Tracks": {str(k): v for k, v in tracks.items()},
        "Playlists": playlists,
    }

    OUT_UNICODE_FOLDERS.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_UNICODE_FOLDERS, "wb") as f:
        plistlib.dump(root, f, fmt=plistlib.FMT_XML)
    print(
        f"Wrote unicode/folders fixture: {OUT_UNICODE_FOLDERS} "
        f"({len(tracks)} tracks, {len(playlists)} playlists)"
    )


if __name__ == "__main__":
    build()
    build_unicode_folders()
