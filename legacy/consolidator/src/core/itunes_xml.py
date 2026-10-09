"""
iTunes / Apple Music "Library.xml" reader and writer.

The XML export (File -> Library -> Export Library) is a standard Apple
property list (plist) with this shape:

<plist version="1.0">
<dict>
    <key>Major Version</key><integer>1</integer>
    <key>Minor Version</key><integer>1</integer>
    <key>Tracks</key>
    <dict>
        <key>1001</key>
        <dict>
            <key>Track ID</key><integer>1001</integer>
            <key>Name</key><string>Song Title</string>
            <key>Artist</key><string>Artist Name</string>
            <key>Album</key><string>Album Name</string>
            <key>Total Time</key><integer>210000</integer>   <!-- ms -->
            <key>Location</key><string>file://localhost/...</string>
            <key>Play Count</key><integer>5</integer>
            <key>Rating</key><integer>80</integer>
            <key>Date Added</key><date>2020-01-01T00:00:00Z</date>
            ...
        </dict>
        ...
    </dict>
    <key>Playlists</key>
    <array>
        <dict>
            <key>Name</key><string>My Playlist</string>
            <key>Playlist ID</key><integer>2001</integer>
            <key>Playlist Items</key>
            <array>
                <dict><key>Track ID</key><integer>1001</integer></dict>
                ...
            </array>
        </dict>
        ...
    </array>
</dict>
</plist>

This is a standard Apple plist (XML variant). Writing (`Library.save`)
uses Python's builtin plistlib directly, which understands this format
natively. Reading (`Library.load`) uses our own incremental parser in
`core/plist_stream.py` -- functionally equivalent to plistlib's XML
reader (same tags, same type coercions) but built to fold each track
into the result as it's parsed rather than building one full in-memory
tree first, which matters at 100k+ track scale. Either way, this module
gives typed access to Tracks and Playlists and writes back a library
that iTunes/Apple Music can re-import, preserving every field we didn't
explicitly change.
"""

from __future__ import annotations

import plistlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .plist_stream import PlistStreamError, StreamingTracksParser


class LibraryParseError(Exception):
    """Raised when the given file is not a readable iTunes/Apple Music XML library."""


def default_library_xml_candidates() -> list[Path]:
    """Common on-disk locations for an iTunes/Apple Music 'Library.xml'
    export, newest-typical-location first. Returns only paths that exist
    on this machine; the caller decides what to do if the list is empty.
    Covers Windows (iTunes) and macOS (iTunes/Music.app) default layouts.
    """
    home = Path.home()
    candidates = [
        # Windows iTunes default (My Music\iTunes\iTunes Music Library.xml
        # is the older name; iTunes Library.xml is the modern export name).
        home / "Music" / "iTunes" / "iTunes Library.xml",
        home / "Music" / "iTunes" / "iTunes Music Library.xml",
        # OneDrive-redirected Music folder, common on managed Windows installs.
        home / "OneDrive" / "Music" / "iTunes" / "iTunes Library.xml",
        # macOS iTunes (pre-Music.app split).
        home / "Music" / "iTunes" / "iTunes Library.xml",
        # macOS Music.app (Catalina+) still exports under the same iTunes folder.
        home / "Music" / "Music" / "Music Library.xml",
    ]
    seen: set[Path] = set()
    found: list[Path] = []
    for c in candidates:
        try:
            resolved = c.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if c.exists() and c.is_file():
            found.append(c)
    return found


def detect_default_library_xml() -> Optional[Path]:
    """Best-guess single default library path, or None if nothing was found
    at any known default location on this machine."""
    candidates = default_library_xml_candidates()
    return candidates[0] if candidates else None


REOPEN_INSTRUCTIONS = (
    "1. Quit iTunes/Apple Music completely (make sure it isn't just minimized — "
    "check it's not still in the taskbar/menu bar).\n"
    "2. Your original Library.xml has been kept — only the new file was written, "
    "nothing was overwritten automatically.\n"
    "3. Replace your working Library.xml with the new file (back up the original "
    "first if you haven't already).\n"
    "   Note: File \u2192 Library \u2192 Import Playlist\u2026 will NOT remove the "
    "duplicates — it only adds tracks and can never remove them, so the old copies "
    "would stay in your main library even with a clean file. Replacing the file and "
    "reopening is the only way iTunes will drop them.\n"
    "4. Reopen iTunes/Apple Music. It only re-reads the library from disk at "
    "startup, so this step can't be skipped — the duplicates will still be showing "
    "in an iTunes window that was already open.\n"
    "5. Spot-check a playlist or two to confirm tracks and play counts look right "
    "before deleting any backups."
)

# Shown instead of REOPEN_INSTRUCTIONS on Windows, where the "\U0001F504
# Rebuild library now..." button on this same dialog already performs
# steps 1, 3, and 4 above for you (quit iTunes, swap the file in,
# relaunch) -- so the manual walkthrough would just be describing work
# a single click already does. Step 2 (nothing overwritten automatically
# until you act) and the spot-check reminder still apply either way, so
# those are kept; only the now-redundant manual how-to is trimmed.
REOPEN_STEPS_AUTOMATED = (
    "Your original Library.xml has been kept — only the new file was written, "
    "nothing was overwritten automatically.\n\n"
    "Click \U0001F504 \u201CRebuild library now\u2026\u201D below and this app will quit "
    "iTunes, back up your existing library, swap in the cleaned file, and "
    "reopen iTunes for you. You'll just need to click \u201CChoose Library...\u201D "
    "yourself when iTunes reopens and asks — that one step can't be automated.\n\n"
    "Afterward, spot-check a playlist or two to confirm tracks and play counts "
    "look right before deleting any backups."
)


@dataclass
class Track:
    """A single track entry. Keeps the raw dict so unknown/unsupported
    fields (artwork refs, sort fields, etc.) are preserved verbatim on write.
    """
    track_id: int
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.raw.get("Name", "") or ""

    @property
    def artist(self) -> str:
        return self.raw.get("Artist", "") or ""

    @property
    def album(self) -> str:
        return self.raw.get("Album", "") or ""

    @property
    def total_time_ms(self) -> int:
        return int(self.raw.get("Total Time", 0) or 0)

    @property
    def location(self) -> Optional[str]:
        return self.raw.get("Location")

    @property
    def bitrate(self) -> int:
        return int(self.raw.get("Bit Rate", 0) or 0)

    @property
    def track_count(self) -> Optional[int]:
        """The album's declared total track count, from the standard
        iTunes/Music "Track Count" tag (e.g. "track 4 of 12" -> 12) --
        distinct from how many of that album's tracks this library
        actually has on file. None when the tag isn't present/set, so
        callers can tell "known to have N tracks" apart from "unknown"
        rather than treating a missing tag as zero."""
        value = self.raw.get("Track Count")
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @property
    def play_count(self) -> int:
        return int(self.raw.get("Play Count", 0) or 0)

    @property
    def rating(self) -> int:
        return int(self.raw.get("Rating", 0) or 0)

    @property
    def date_added(self):
        return self.raw.get("Date Added")

    def completeness_score(self) -> float:
        """Heuristic used to pick the 'best' canonical track among duplicates.
        Higher is better. Combines metadata completeness with audio quality
        proxies (bitrate), since we do not read audio streams in v1.
        """
        score = 0.0
        # Reward presence of descriptive metadata fields.
        for key in ("Name", "Artist", "Album", "Genre", "Year", "Composer", "Album Artist"):
            if self.raw.get(key):
                score += 1.0
        # Reward artwork.
        if self.raw.get("Artwork Count", 0):
            score += 2.0
        # Reward higher bitrate (quality proxy), scaled down.
        score += min(self.bitrate, 320) / 100.0
        # Slightly reward higher play count / rating as a "this copy is the
        # one actually used" signal, without letting it dominate metadata.
        score += min(self.play_count, 50) / 50.0
        score += self.rating / 100.0
        return score


@dataclass
class Playlist:
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.raw.get("Name", "") or ""

    @property
    def playlist_id(self) -> Optional[int]:
        return self.raw.get("Playlist ID")

    @property
    def is_smart(self) -> bool:
        """True for an iTunes "smart playlist" -- one whose membership is
        computed by iTunes/Music.app itself from a set of rules (e.g.
        "Genre is Jazz and Rating > 3 stars"), not a fixed track list we
        control. Library.xml marks these with a "Smart Info" key (present)
        and, when there are actual criteria, a "Smart Criteria" key holding
        an opaque binary-plist blob -- Apple's own undocumented, version-
        varying encoding for the rule tree, not something this app parses
        or evaluates (see core/consolidator.smart_playlist_merge_warnings
        for what this is used for instead: flagging *possible* impact
        without claiming to know the actual rules)."""
        return self.raw.get("Smart Info") is not None

    @property
    def is_special(self) -> bool:
        """iTunes built-in playlists (Library, Music, Downloaded, etc.) that
        should never be treated as user playlists for consolidation purposes."""
        return bool(
            self.raw.get("Master")
            or self.raw.get("Music")
            or self.raw.get("Movies")
            or self.raw.get("TV Shows")
            or self.raw.get("Podcasts")
            or self.raw.get("Audiobooks")
            or self.raw.get("Purchased on Device")
            or self.is_smart  # smart playlists: leave rules alone
        )

    def track_ids(self) -> list[int]:
        items = self.raw.get("Playlist Items", []) or []
        return [it["Track ID"] for it in items if "Track ID" in it]

    def set_track_ids(self, ids: list[int]) -> None:
        self.raw["Playlist Items"] = [{"Track ID": tid} for tid in ids]


@dataclass
class Library:
    raw: dict[str, Any]
    tracks: dict[int, Track]
    playlists: list[Playlist]
    source_path: Optional[Path] = None

    @staticmethod
    def tracks_from_raw(raw_tracks: dict) -> dict[int, "Track"]:
        """Shared 'Tracks dict-of-dicts -> {track_id: Track}' conversion,
        used both for a freshly-parsed library and for rehydrating a
        library from an in-memory snapshot (see cache_db snapshots /
        main_window's restore-backup flow), so the two paths can never
        drift out of sync with each other."""
        tracks: dict[int, Track] = {}
        for key, entry in (raw_tracks or {}).items():
            if entry is None:
                continue
            try:
                tid = int(entry.get("Track ID", key))
            except (TypeError, ValueError):
                continue
            tracks[tid] = Track(track_id=tid, raw=entry)
        return tracks

    @classmethod
    def load(
        cls,
        path: Path,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> "Library":
        """Parses the given iTunes/Music Library.xml export.

        Uses an incremental (streaming) XML parser rather than loading
        the whole document into one in-memory tree and then walking it a
        second time to build the tracks map: each track is converted to
        a `Track` and folded into the result in the same pass it's
        parsed. `library.raw["Tracks"]` is fully repopulated (using the
        same dict objects, not copies) before this method returns, so
        `library.raw` is always complete -- see core/plist_stream.py for
        what this does and does not save in memory.

        `on_progress`, if given, is called periodically as
        `on_progress(tracks_parsed_so_far, None)` while parsing (the
        second argument is always None since the total track count isn't
        known until parsing finishes) -- optional, purely additive, and
        safe to omit; existing callers that don't pass it see no change
        in behavior.
        """
        tracks: dict[int, Track] = {}

        def on_track(key: str, entry: dict) -> None:
            try:
                tid = int(entry.get("Track ID", key))
            except (TypeError, ValueError):
                return
            tracks[tid] = Track(track_id=tid, raw=entry)
            if on_progress is not None and tracks and len(tracks) % 2000 == 0:
                on_progress(len(tracks), None)

        try:
            with open(path, "rb") as f:
                parser = StreamingTracksParser(on_track=on_track)
                raw = parser.parse(f)
        except PlistStreamError as exc:
            raise LibraryParseError(
                f"Could not parse '{path.name}' as an iTunes XML library plist: {exc}"
            ) from exc
        except Exception as exc:  # any other I/O or parser error
            raise LibraryParseError(
                f"Could not parse '{path.name}' as an iTunes XML library plist: {exc}"
            ) from exc

        if not isinstance(raw, dict) or "Tracks" not in raw:
            raise LibraryParseError(
                f"'{path.name}' does not look like an iTunes Library.xml export "
                "(missing top-level 'Tracks' dict). Export via "
                "File -> Library -> Export Library in Apple Music/iTunes."
            )

        # The streaming parser hands each track's dict to `on_track` and
        # then drops its own reference (leaving a `None` placeholder in
        # raw["Tracks"]) so the two don't stay duplicated in memory during
        # parsing. Re-attach the *same* dict objects (no copying -- these
        # are the exact objects each Track.raw already points to) so
        # raw["Tracks"] is fully populated again before this method
        # returns. This matters because callers rely on `library.raw`
        # containing the complete, real library data -- notably the
        # auto-backup/pre-consolidation snapshots in core/workers.py,
        # which pass `library.raw` straight to CacheDB.save_snapshot().
        # This is a cheap reference re-link (dict of pointers), not a
        # rebuild of the track data itself, so it doesn't reintroduce the
        # memory cost the streaming parse avoided.
        raw["Tracks"] = {str(t.track_id): t.raw for t in tracks.values()}

        playlists = [Playlist(raw=p) for p in (raw.get("Playlists") or [])]

        return cls(raw=raw, tracks=tracks, playlists=playlists, source_path=path)

    def save(self, path: Path) -> None:
        """Write the library back out as a valid iTunes-importable XML plist.
        Rebuilds the Tracks/Playlists sections from our (possibly modified)
        objects while leaving every other top-level key untouched."""
        out = dict(self.raw)  # shallow copy of top-level dict; unknown keys preserved
        out["Tracks"] = {str(t.track_id): t.raw for t in self.tracks.values()}
        out["Playlists"] = [p.raw for p in self.playlists]

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            plistlib.dump(out, f, fmt=plistlib.FMT_XML, sort_keys=False)

    def user_playlists(self) -> list[Playlist]:
        return [p for p in self.playlists if not p.is_special]

    def save_back_to_source(self) -> Path:
        """Writes the (possibly modified) library back to the exact path it
        was loaded from — the 'direct write-back' path, for users who want
        to overwrite their working Library.xml in place rather than saving
        a separate consolidated copy. Raises if the library wasn't loaded
        from a file (e.g. rehydrated from a backup snapshot in memory)."""
        if self.source_path is None:
            raise LibraryParseError(
                "This library has no known source file to write back to; "
                "use Save As instead."
            )
        self.save(self.source_path)
        return self.source_path
