"""
Library Health -> direct fix actions.

core/library_health.py only ever *reports* issues (missing artwork,
missing/broken file locations, etc.) -- nothing there mutates the
library. This module is the read/write counterpart: small, targeted
functions that actually fix one flagged track at a time, called directly
from the Health tab's per-issue action buttons (see ui/health_panel.py)
instead of only ever showing a count.

Both actions here only ever touch the in-memory Library the rest of the
app already has open (specifically `track.raw`, the same dict object
`Library.save()`/`save_back_to_source()` serialize from) -- neither
function writes to disk on its own. The existing "Clean up duplicates"/
write-back flow (or File > Save audit report's sibling, a plain re-save)
is what actually persists the change, exactly as manual review edits
(mark not-duplicate, change canonical pick) already work elsewhere in
this app. This keeps every action here safe to try and undo (by simply
not saving) without a separate undo mechanism.

Deliberately offline: "fix missing artwork" does NOT reach out to any
web/API artwork source. This app has no network dependency today (see
requirements.txt) and no user-facing setting for where a fetched image
would come from or how it'd be verified as the right cover -- silently
adding a network call here would be a much bigger change than a bug-fix/
small-feature pass should make, and would need its own review (API
choice, rate limits, offline behavior, a source citation for the image).
Instead, this offers what the library's own local data can actually
support: copying embedded artwork from another on-disk copy of the same
song when one exists (common right after a fuzzy-duplicate scan finds
near-matches where only one copy happens to have art), which is honest
about what it can find and never fabricates or downloads anything.

A third action, find_missing_files_in_root(), does the same job as
relink_track_location() but for many tracks at once: given one root
folder, it looks for every missing/broken-Location track's file by
filename anywhere under that folder (recursively), for the common case
of a whole music folder having been moved or reorganized into different
subfolders. Like the two actions above, it only ever returns candidate
matches for review -- applying one is still a relink_track_location()
call the caller makes explicitly, so nothing is relinked automatically.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote

from .artwork import file_uri_to_path, read_embedded_artwork
from .duplicate_detector import normalize
from .itunes_xml import Library, Track


def path_to_file_uri(path: Path) -> str:
    """Inverse of artwork.file_uri_to_path -- builds a Library.xml-style
    'file://localhost/...' Location string from a local filesystem path,
    matching the exact form iTunes itself writes (see itunes_xml.py's
    module docstring and artwork.file_uri_to_path's Windows drive-letter
    handling, which this mirrors on the way back out)."""
    resolved = str(path)
    # Windows drive-letter paths ("C:\Users\...") need a leading slash
    # before the drive letter once converted to forward slashes, matching
    # the "/C:/Users/..." shape file_uri_to_path strips off on the way
    # in. POSIX paths already start with "/" and are used as-is.
    posix = resolved.replace("\\", "/")
    if len(posix) >= 2 and posix[1] == ":":
        posix = "/" + posix
    return "file://localhost" + quote(posix)


@dataclass
class RelinkResult:
    ok: bool
    message: str


def relink_track_location(track: Track, new_path: Path) -> RelinkResult:
    """Points `track` at `new_path` on disk, fixing a missing/broken file
    Location flagged by library_health.analyze_library
    (missing_or_broken_location). Mutates track.raw in place (the same
    dict Library.save() serializes from) -- does not touch anything else
    about the track (name, artist, play count, ratings, playlists all
    stay exactly as they were), and never writes to disk itself; the
    normal save/write-back flow persists this the next time the user
    saves, same as any other in-memory edit."""
    if not new_path.exists():
        return RelinkResult(False, f"'{new_path.name}' does not exist.")
    if not new_path.is_file():
        return RelinkResult(False, f"'{new_path.name}' is not a file.")
    track.raw["Location"] = path_to_file_uri(new_path)
    # "Size" is one of the few fields iTunes itself keeps in sync with
    # the actual audio file (used elsewhere in this app for the Health
    # tab's storage-savings estimate -- see library_health._track_file_size)
    # -- refreshed here so relinking doesn't leave a stale size from
    # whatever file used to be at the old Location. Best-effort: a size
    # lookup failing (permissions, races) never blocks the relink itself.
    try:
        track.raw["Size"] = new_path.stat().st_size
    except OSError:
        pass
    return RelinkResult(True, f"Relinked to '{new_path.name}'.")


@dataclass
class ArtworkSource:
    """One other on-disk copy of (likely) the same song that has embedded
    artwork this track doesn't -- a candidate to copy art from, not yet
    applied. Kept as a dataclass (rather than immediately writing) so the
    Health tab can show the candidate to the user (which file, its
    artist/album) before committing, matching this app's existing
    "review before write" pattern."""
    track_id: int
    path: Path
    display_name: str


def find_artwork_source(
    library: Library, target: Track, max_candidates: int = 1
) -> list[ArtworkSource]:
    """Looks for another track in the same library that (a) normalizes to
    the same artist+title as `target` (the same identity check
    duplicate_detector.py's exact-match tier already uses -- see
    duplicate_detector.normalize/DuplicateGroup) and (b) has a local
    audio file with embedded artwork readable via
    core.artwork.read_embedded_artwork. This is exactly the situation a
    fuzzy/exact duplicate scan already surfaces (two copies of the same
    song, one better-tagged than the other) looked at from the artwork
    angle specifically. Returns at most `max_candidates` matches, cheapest
    first (their own bitrate isn't compared -- any readable embedded
    image is equally useful as a copy source here). Never touches the
    target track; purely a lookup."""
    target_key = (normalize(target.artist), normalize(target.name))
    if not target_key[0] and not target_key[1]:
        return []

    results: list[ArtworkSource] = []
    for other in library.tracks.values():
        if other.track_id == target.track_id:
            continue
        if (normalize(other.artist), normalize(other.name)) != target_key:
            continue
        path = file_uri_to_path(other.location) if other.location else None
        if path is None or not path.exists():
            continue
        if read_embedded_artwork(path) is None:
            continue
        results.append(
            ArtworkSource(
                track_id=other.track_id,
                path=path,
                display_name=f"{other.artist or 'Unknown artist'} \u2014 {other.name or path.name}",
            )
        )
        if len(results) >= max_candidates:
            break
    return results


@dataclass
class ArtworkFixResult:
    ok: bool
    message: str


def apply_artwork_from_source(
    library: Library, target: Track, source: ArtworkSource
) -> ArtworkFixResult:
    """Confirms `source` still has readable artwork and marks `target` as
    having artwork available from that other copy.

    iTunes/Apple Music's own "Artwork Count" field only ever reflects art
    actually embedded in *that* track's own audio file -- this app does
    not write audio-file tags (see core/artwork.py's module docstring:
    read-only, dependency-free parsing, no write path for any audio
    format). Setting "Artwork Count" here without actually embedding an
    image in `target`'s own file would make the Health tab's "Missing
    cover art" count silently wrong the next time this app re-scans,
    which is worse than being transparent about the limitation. Instead,
    this records which other track's file the art can be copied from
    (target.raw["Artwork Source Track ID"]) so the duplicate-review UI
    can surface "art available from another copy" next to this track,
    and returns a result the caller can present -- e.g. pointing the
    user at their OS/player's own "embed artwork" step, or simply noting
    that consolidating the duplicate group (removing this copy in favor
    of the one that already has art) is the more direct fix."""
    if read_embedded_artwork(source.path) is None:
        return ArtworkFixResult(
            False, f"'{source.path.name}' no longer has readable artwork."
        )
    target.raw["Artwork Source Track ID"] = source.track_id
    return ArtworkFixResult(
        True,
        f"Found artwork on another copy of this song ({source.display_name}). "
        "This app can't embed artwork into an audio file directly, but "
        "keeping (or making canonical) that copy during clean-up carries "
        "its artwork forward.",
    )


def missing_artwork_candidates_available(library: Library, target: Track) -> bool:
    """Cheap existence check (no Path.stat() beyond what find_artwork_source
    already needs) used by the Health tab to decide whether to show a
    "Fix missing artwork" action at all for a given track, vs. only "no
    other copy with artwork found"."""
    return bool(find_artwork_source(library, target, max_candidates=1))


@dataclass
class MissingFileMatch:
    """One track flagged by library_health.analyze_library as having a
    missing/broken Location (missing_or_broken_location -- the same set
    shown next to a "!" by iTunes/Apple Music itself) for which a file
    with the same filename was found somewhere under a user-selected root
    folder. Kept as a dataclass (rather than immediately relinking) so
    the caller can show the match -- old vs. found path -- before
    applying it, the same "review before write" pattern find_artwork_source
    /ArtworkSource already follows above."""
    track_id: int
    display_name: str
    old_location: str  # raw Library.xml Location string, "" if it had none
    found_path: Path


def find_missing_files_in_root(
    library: Library,
    root_folder: Path,
    track_ids: Optional[list[int]] = None,
) -> list[MissingFileMatch]:
    """Searches `root_folder` (recursively) for files that match the
    filename of each library track whose Location is missing/broken
    (library_health.HealthReport.missing_or_broken_location), and returns
    one MissingFileMatch per track a match was found for.

    Written for the case this exists to cover: the user reorganized their
    music into a different subfolder layout under the iTunes folder (or
    moved it to a new drive/folder entirely) and iTunes/Apple Music now
    shows a "!" next to every track whose old path no longer resolves.
    Individually relocating each one with "Locate missing file..." is
    impractical once there are more than a handful, so this does the same
    lookup as that action -- just across every missing track under one
    folder the user points at once, instead of one file dialog per track.

    Matching is by filename only (case-insensitive), not by tag content:
    this app doesn't read tags from files that can't be found in the
    first place, and a filename match is exactly what "the same files,
    moved" produces. Track order is undefined (os.walk order), and if
    more than one file under `root_folder` shares the same filename, the
    first one encountered is used -- ambiguous beyond that is a rename/
    dedupe problem this app already handles elsewhere (Duplicates tab),
    not one this lookup tries to resolve on its own.

    `track_ids` restricts the search to that subset (e.g. a HealthReport
    already computed this pass); when omitted, every track with a
    missing/broken Location in `library.tracks` is considered by
    re-deriving that check locally (mirrors
    library_health._location_missing_or_unreachable's local-path check,
    without that function's own time budget, since a single explicit
    "search this folder" action is expected to take as long as it takes).
    Never touches the track itself -- like relink_track_location, callers
    apply a chosen MissingFileMatch by calling that same function with
    match.found_path."""
    if track_ids is None:
        candidates = [t for t in library.tracks.values() if _is_missing_locally(t)]
    else:
        candidates = [
            library.tracks[tid] for tid in track_ids if tid in library.tracks
        ]
    if not candidates:
        return []

    # filename (lowercased) -> first matching path found under root_folder.
    # Location is a "file://" URI (see itunes_xml.py's module docstring),
    # so its filename segment is percent-encoded (e.g. "Song%20A.mp3" for
    # "Song A.mp3" on disk) -- unquote() before comparing, or a Location
    # containing a space, unicode character, or other encoded byte would
    # never match the real on-disk filename it actually corresponds to.
    by_filename: dict[str, Path] = {}
    wanted = {
        unquote(loc.rsplit("/", 1)[-1]).lower()
        for t in candidates
        if (loc := (t.raw.get("Location") or ""))
    }
    wanted.discard("")
    if not wanted:
        return []
    for dirpath, _dirnames, filenames in os.walk(root_folder):
        for fname in filenames:
            key = fname.lower()
            if key in wanted and key not in by_filename:
                by_filename[key] = Path(dirpath) / fname
        if len(by_filename) == len(wanted):
            break  # every wanted filename accounted for; no need to keep walking

    results: list[MissingFileMatch] = []
    for track in candidates:
        loc = track.raw.get("Location") or ""
        if not loc:
            continue
        filename = unquote(loc.rsplit("/", 1)[-1])
        found = by_filename.get(filename.lower())
        if found is None:
            continue
        results.append(
            MissingFileMatch(
                track_id=track.track_id,
                display_name=f"{track.artist or 'Unknown artist'} \u2014 {track.name or filename}",
                old_location=loc,
                found_path=found,
            )
        )
    return results


def _is_missing_locally(track: Track) -> bool:
    """Local-path-only re-check of whether `track` currently has a
    missing/broken Location, mirroring
    library_health._location_missing_or_unreachable but without that
    function's shared time budget (see find_missing_files_in_root's
    docstring for why this function accepts taking longer)."""
    loc = track.raw.get("Location") or ""
    if not loc:
        return True
    if not loc.startswith("file://"):
        return False
    path = file_uri_to_path(loc)
    if path is None:
        return False
    try:
        return not path.exists()
    except OSError:
        return False
