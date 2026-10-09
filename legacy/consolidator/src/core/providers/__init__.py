"""
Streaming-service provider plugin architecture.

This package defines a small, stable interface (`LibraryProvider`) that any
streaming-service integration implements, plus a registry
(`register_provider`/`get_provider`/`available_providers`) other code in
this app uses to discover them, so `core/consolidator.py`, `ui/*`, etc.
never need to import a specific service by name.

Importing this package registers every provider that's actually ready for
use -- today that's just `spotify_export.SpotifyExportProvider` (a working,
offline, read-only import from a Spotify data-export .zip/folder; see that
module's docstring). `apple_music_api.py` stays deliberately unimported/
unregistered here: it's still a skeleton whose methods just raise "not
implemented yet" (see that module's docstring), and only a provider that
genuinely works should ever show up in `available_providers()`.

This package existing does not, by itself, change how Library.xml is read
or written -- `core/itunes_xml.py` remains the only thing that touches a
Library.xml file. A registered provider only ever produces
ProviderTrack/ProviderPlaylist objects (see base.py) for the app to
*compare against* an already-loaded Library; nothing here writes back to
Library.xml or to a provider's own data.

Usage:

    from .core.providers import available_providers, get_provider
    for provider in available_providers():
        ...

Adding a new provider module: give it the same shape as
spotify_export.py (subclass LibraryProvider, implement whichever of
import_tracks/import_playlists/export_tracks its `capabilities` promise,
call `register_provider(...)` at module import time), then import that
module below so importing this package registers it.
"""

from __future__ import annotations

from .base import (
    ProviderCapability,
    ProviderError,
    ProviderPlaylist,
    ProviderTrack,
    LibraryProvider,
    available_providers,
    get_provider,
    register_provider,
)

# Imported for its registration side effect (see module docstring above
# and spotify_export.py's own bottom-of-file register_provider(...) call).
# apple_music_api.py is intentionally NOT imported here -- it's still a
# not-yet-working skeleton (see that module's docstring) and should not
# appear in available_providers() until it actually does something.
from . import spotify_export as _spotify_export  # noqa: F401

__all__ = [
    "ProviderCapability",
    "ProviderError",
    "ProviderPlaylist",
    "ProviderTrack",
    "LibraryProvider",
    "available_providers",
    "get_provider",
    "register_provider",
]
