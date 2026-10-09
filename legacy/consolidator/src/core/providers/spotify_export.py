"""
Spotify export provider -- reads a user's own Spotify data export (the
JSON bundle from Spotify's Settings -> Account -> Privacy -> "Download
your data") into ProviderTrack/ProviderPlaylist objects, matching the
plugin interface in core/providers/base.py.

Export-file-based rather than a live API integration, since that export
needs no API credentials/OAuth, is the more approachable starting point
(see the design rationale this module originally shipped with), and
Spotify's own user-facing export is what most people asking for "Spotify
support" actually have in hand. A live Spotify Web API path (OAuth + REST
calls) would be a second, separate capability on top of this if
real-time (not export-snapshot) access is ever wanted -- that would need
an HTTP client dependency, added at that point, in this module only.
`import_tracks`/`import_playlists` below are read-only: nothing here
writes to the export, to Library.xml, or anywhere else.

Accepts either the export .zip exactly as Spotify emails/hands it out, or
a folder it's already been extracted into -- both are handled the same
way (see `_read_export_json_files`), searching any depth of
subfolder for the files it needs rather than assuming a fixed layout,
since Spotify's own zip has changed its internal folder nesting over
time and this app has no control over that.

Known files this reads, both stdlib-`json`-parseable (no new dependency
needed, matching providers/base.py's "no new required dependency"
design goal):

  - YourLibrary.json: `{"tracks": [{"artist", "album", "track", "uri"}, ...],
    ...}` -- saved-tracks library. Only the "tracks" key is used;
    "albums"/"artists"/"shows"/"episodes"/etc. are outside what this
    provider models today (see ProviderTrack/ProviderPlaylist -- there's
    no album- or show-level shape to put them in yet).
  - Playlist1.json, Playlist2.json, ... (older exports) or a single
    Playlists.json (newer exports): `{"playlists": [{"name", "items":
    [{"track": {"trackName", "artistName", "albumName", "trackUri"}},
    ...]}, ...]}`. Podcast-episode entries inside a playlist (where
    "track" is null and "episode" is set instead) are skipped -- this
    provider only models tracks, matching ProviderTrack's shape.

Spotify has changed this export's exact field names/layout before and
may again; every lookup below is defensive (`.get(...)` with fallbacks,
never a bare `[...]` on a key that might be absent) so an unrecognized or
partial export degrades to "fewer items found" rather than a crash, and
`import_tracks`/`import_playlists` raise ProviderError with a specific,
actionable message when nothing recognizable is found at all rather than
silently returning an empty result that looks like a real (empty)
library.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Iterable

from .base import (
    LibraryProvider,
    ProviderCapability,
    ProviderError,
    ProviderPlaylist,
    ProviderTrack,
    register_provider,
)

# Spotify's own export has used both a "YourLibrary.json" and (in at
# least one export revision) "YourLibrary1.json" naming -- matched
# case-insensitively against just the filename (not the full path/
# subfolder, which has also varied) so either is found regardless of
# where inside the zip/folder it landed.
_LIBRARY_FILENAME_PREFIX = "yourlibrary"

# Matches "Playlist1.json", "Playlist2.json", ... (the classic per-batch
# export) as well as a single "Playlists.json" (seen in newer exports) --
# both shapes carry the same top-level {"playlists": [...]} structure, so
# one loader (_extract_playlists_from_payload) handles either.
_PLAYLIST_FILENAME_PREFIX = "playlist"


def _iter_export_json_members(source: Path) -> Iterable[tuple[str, str]]:
    """Yields (display_name, text) for every .json file found under
    `source`, which may be a directory (already-extracted export) or a
    .zip file (the export exactly as downloaded) -- searched at any
    depth, since Spotify's own zip layout/nesting has changed across
    export revisions and this app has no control over that. Files that
    fail to decode as UTF-8 text are skipped rather than raising, since a
    single unrelated/binary file elsewhere in the export (this app only
    ever needs a couple of specific ones) should never block reading the
    ones that matter.
    """
    if source.is_dir():
        for path in source.rglob("*.json"):
            try:
                yield path.name, path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
        return

    if source.is_file() and source.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(source) as zf:
                for info in zf.infolist():
                    if info.is_dir() or not info.filename.lower().endswith(".json"):
                        continue
                    try:
                        text = zf.read(info).decode("utf-8")
                    except (UnicodeDecodeError, zipfile.BadZipFile):
                        continue
                    yield Path(info.filename).name, text
        except (OSError, zipfile.BadZipFile) as exc:
            raise ProviderError(
                f"Couldn't open '{source.name}' as a Spotify export zip: {exc}"
            ) from exc
        return

    raise ProviderError(
        f"'{source}' is neither a folder nor a .zip file -- select the "
        "folder you extracted your Spotify export into, or the .zip "
        "exactly as downloaded from Spotify."
    )


def _extract_library_tracks(payload: dict) -> list[ProviderTrack]:
    """Reads the "tracks" list out of one parsed YourLibrary.json payload.
    Each entry's own fields are read defensively (missing name/artist
    becomes an empty string, matching how core/itunes_xml.Track already
    treats absent fields elsewhere in this app) since a track with an
    unrecognized shape is still worth surfacing rather than dropping
    entirely -- an empty artist/title is something the app's existing
    duplicate-matching (core/duplicate_detector.normalize) already
    tolerates.
    """
    tracks: list[ProviderTrack] = []
    for entry in payload.get("tracks") or []:
        if not isinstance(entry, dict):
            continue
        uri = str(entry.get("uri") or entry.get("trackUri") or "")
        tracks.append(
            ProviderTrack(
                external_id=uri,
                name=str(entry.get("track") or entry.get("trackName") or ""),
                artist=str(entry.get("artist") or entry.get("artistName") or ""),
                album=str(entry.get("album") or entry.get("albumName") or ""),
                raw=entry,
            )
        )
    return tracks


def _extract_playlists_from_payload(payload: dict) -> list[ProviderPlaylist]:
    """Reads the "playlists" list out of one parsed Playlist*.json /
    Playlists.json payload. Each playlist's "items" entries can be either
    a track or a podcast episode (see module docstring) -- only track
    entries are kept, matching ProviderPlaylist/ProviderTrack, which have
    no episode shape to hold the rest.
    """
    playlists: list[ProviderPlaylist] = []
    for entry in payload.get("playlists") or []:
        if not isinstance(entry, dict):
            continue
        track_uris: list[str] = []
        for item in entry.get("items") or []:
            if not isinstance(item, dict):
                continue
            track = item.get("track")
            if not isinstance(track, dict):
                # Podcast episode (track is null, "episode" holds the
                # data instead) or an otherwise-unrecognized item shape --
                # neither has a place in ProviderTrack today, so skipped
                # rather than guessed at.
                continue
            uri = track.get("trackUri") or track.get("uri")
            if uri:
                track_uris.append(str(uri))
        playlists.append(
            ProviderPlaylist(
                external_id=str(entry.get("name") or ""),
                name=str(entry.get("name") or "Untitled playlist"),
                track_external_ids=track_uris,
                raw=entry,
            )
        )
    return playlists


class SpotifyExportProvider(LibraryProvider):
    """Reads tracks and playlists from a Spotify data-export bundle (a
    .zip or an already-extracted folder) into ProviderTrack/
    ProviderPlaylist objects the rest of this app can compare against a
    Library.xml Library using the existing matching logic in
    core/duplicate_detector.py (see base.py's module docstring for why
    ProviderTrack mirrors Track's shape).

    Registered by default (see the bottom of this module) -- unlike
    apple_music_api.py's still-skeleton provider, this one is a genuine,
    working, offline, read-only import: no network access, no
    credentials, and it never writes back to the export or to
    Library.xml.
    """

    provider_id = "spotify_export"
    display_name = "Spotify (exported library)"
    capabilities = frozenset({ProviderCapability.IMPORT})

    def validate_source(self, source: Any) -> str | None:
        path = Path(source) if source is not None else None
        if path is None or not path.exists():
            return "Select the folder or .zip from your Spotify data export."
        if path.is_file() and path.suffix.lower() != ".zip":
            return "Select the .zip Spotify emailed you, or the folder you extracted it into."
        return None

    def import_tracks(self, source: Any) -> Iterable[ProviderTrack]:
        path = Path(source) if source is not None else None
        if path is None or not path.exists():
            raise ProviderError(
                "Select the folder or .zip from your Spotify data export."
            )
        tracks: list[ProviderTrack] = []
        found_library_file = False
        for name, text in _iter_export_json_members(path):
            if not name.lower().startswith(_LIBRARY_FILENAME_PREFIX):
                continue
            found_library_file = True
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                tracks.extend(_extract_library_tracks(payload))
        if not found_library_file:
            raise ProviderError(
                "No 'YourLibrary.json' found in that export. Make sure "
                "you selected the full Spotify data export (Settings -> "
                "Account -> Privacy -> \"Download your data\"), not a "
                "single unrelated file."
            )
        return tracks

    def import_playlists(self, source: Any) -> Iterable[ProviderPlaylist]:
        path = Path(source) if source is not None else None
        if path is None or not path.exists():
            raise ProviderError(
                "Select the folder or .zip from your Spotify data export."
            )
        playlists: list[ProviderPlaylist] = []
        for name, text in _iter_export_json_members(path):
            lowered = name.lower()
            if not lowered.startswith(_PLAYLIST_FILENAME_PREFIX):
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                playlists.extend(_extract_playlists_from_payload(payload))
        # Deliberately not a ProviderError when empty: "no playlists"
        # (e.g. a library-only export, or an account with none saved) is
        # a valid, common answer -- matching LibraryProvider.
        # import_playlists' own documented default behavior for an
        # IMPORT-capable provider with no playlist data.
        return playlists


# Registered at import time (unlike apple_music_api.py, which stays
# unregistered -- that one's methods still just raise "not implemented
# yet"). Importing this module is enough to make "Spotify (exported
# library)" show up anywhere the app calls available_providers()/
# get_provider("spotify_export"); see core/providers/__init__.py, which
# imports this module for exactly that reason.
register_provider(SpotifyExportProvider())
