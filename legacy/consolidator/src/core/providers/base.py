"""
Base interface + registry for streaming-service providers.

Design goals, matching how the rest of this app is built:

  - No new required dependency. This module is stdlib-only. A concrete
    provider that needs an HTTP client, an OAuth flow, etc. imports what
    it needs itself, inside its own module -- so a build that doesn't
    ship/enable that provider never has to install it. (Today, none are
    registered by default; see the module docstring in __init__.py.)

  - Same shape as the app's existing data, not a parallel one.
    `ProviderTrack` mirrors the handful of fields `core/itunes_xml.Track`
    already exposes as properties (name/artist/album/etc.), so matching a
    provider track against a Library.xml `Track` can reuse
    `core/duplicate_detector.py`'s existing comparison logic unchanged
    rather than needing a second matcher. This module does not itself
    call into duplicate_detector -- it only shapes the data so that a
    future integration can, without another translation layer.

  - Explicit, inspectable capabilities. A provider declares what it can
    do (`capabilities`) rather than the app trying isinstance()/hasattr()
    checks or every provider being forced to implement every method --
    e.g. a read-only export-based integration (Spotify, via its data
    export) never needs to implement `export_tracks`, and the UI can grey
    out an action a provider doesn't support instead of it raising.

  - Registry, not a hardcoded import list. `register_provider()` is a
    plain in-memory dict keyed by `provider_id`; nothing calls it yet
    (see __init__.py), so registering zero providers is the correct,
    fully-backward-compatible state -- existing Library.xml
    load/consolidate/save behavior is entirely untouched by this module
    existing.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional


class ProviderCapability(Enum):
    """What a provider integration can actually do. A provider declares
    the subset it supports via `LibraryProvider.capabilities`; callers
    check membership (e.g. `ProviderCapability.IMPORT in provider.capabilities`)
    instead of assuming every provider implements every method."""

    # Read tracks/playlists from the service (or from an export file the
    # service produced) into ProviderTrack/ProviderPlaylist objects the
    # app can compare against a Library.xml Library.
    IMPORT = "import"

    # Write/sync the app's cleaned-up library back out to the service
    # (e.g. update playlists, play counts) rather than only reading from it.
    EXPORT = "export"

    # Provider requires an interactive auth step (OAuth, API key entry,
    # etc.) before IMPORT/EXPORT can be used -- lets the UI show a
    # "Connect..." step instead of only surfacing an auth failure later.
    REQUIRES_AUTH = "requires_auth"


class ProviderError(Exception):
    """Raised by a provider implementation for any integration-specific
    failure (auth failure, malformed export, network/API error, etc.).
    Callers can catch this one type without needing to know which
    concrete provider raised it, matching how core/errors.py's
    with_recovery_guidance() is used elsewhere in this app for
    presenting a caught exception's message to the user."""


@dataclass
class ProviderTrack:
    """A single track as read from a provider, in the same shape as
    `core/itunes_xml.Track`'s properties (name/artist/album/etc.) so it
    can be compared against a Library.xml Track using the app's existing
    matching logic (see core/duplicate_detector.py) without a separate
    translation step once a real integration exists.

    `external_id` is the provider's own identifier for the track (e.g. a
    Spotify track URI or an Apple Music catalog ID) -- kept distinct from
    Library.xml's integer Track ID since the two id spaces are unrelated
    and must never be conflated.

    `raw` mirrors `core/itunes_xml.Track.raw`'s "keep everything, even
    fields this app doesn't model yet" approach, so a provider can carry
    extra service-specific fields (e.g. Spotify's popularity score)
    through to anywhere that might want them later without a schema
    change here.
    """

    external_id: str
    name: str
    artist: str
    album: str = ""
    duration_ms: int = 0
    isrc: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderPlaylist:
    """A single playlist as read from a provider, analogous to
    `core/itunes_xml.Playlist`."""

    external_id: str
    name: str
    track_external_ids: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class LibraryProvider(abc.ABC):
    """Base class every streaming-service integration implements.

    Concrete subclasses set the three class attributes below and
    implement whichever of import_tracks/export_tracks their declared
    `capabilities` promise. Methods for a capability a provider doesn't
    declare are free to stay unimplemented (the ABC does not require
    every method to be overridden) -- callers are expected to check
    `capabilities` first, exactly as documented on ProviderCapability.
    """

    #: Stable machine identifier, e.g. "apple_music_api", "spotify_export".
    #: Used as the registry key -- must be unique across all providers.
    provider_id: str = ""

    #: Human-readable name shown in the UI, e.g. "Apple Music (API)".
    display_name: str = ""

    #: Subset of ProviderCapability this provider actually supports.
    capabilities: frozenset[ProviderCapability] = frozenset()

    def import_tracks(self, source: Any) -> Iterable[ProviderTrack]:
        """Reads tracks from the service/export named or referenced by
        `source` (a provider-specific value -- a file path for an
        export-based provider, an already-authenticated client/session
        for an API-based one, etc.). Only meaningful when
        ProviderCapability.IMPORT is declared; raises NotImplementedError
        otherwise so a capability mismatch fails loudly instead of
        silently returning nothing."""
        raise NotImplementedError(
            f"{self.provider_id or type(self).__name__} does not support import"
        )

    def import_playlists(self, source: Any) -> Iterable[ProviderPlaylist]:
        """Reads playlists from the service/export. Optional even for an
        IMPORT-capable provider (e.g. a track-only export format) --
        default implementation returns no playlists rather than raising,
        since "no playlists" is a valid, common answer."""
        return []

    def export_tracks(self, tracks: Iterable[ProviderTrack], destination: Any) -> None:
        """Writes/syncs `tracks` back out to the service. Only meaningful
        when ProviderCapability.EXPORT is declared; raises
        NotImplementedError otherwise."""
        raise NotImplementedError(
            f"{self.provider_id or type(self).__name__} does not support export"
        )

    def validate_source(self, source: Any) -> Optional[str]:
        """Best-effort, cheap pre-check of whether `source` looks usable
        for this provider (file exists and has the expected extension,
        an API token is present, etc.) -- returns None if it looks fine,
        or a short user-facing reason string if not. Intentionally not
        exhaustive/authoritative: the real read in import_tracks() is
        still expected to raise ProviderError on anything this missed.
        Default implementation always passes (returns None) so a
        provider that hasn't written a real check yet doesn't block
        anything."""
        return None


# --------------------------------------------------------------------- registry

_REGISTRY: dict[str, LibraryProvider] = {}


def register_provider(provider: LibraryProvider) -> None:
    """Adds `provider` to the in-memory registry, keyed by its
    provider_id. Registering the same provider_id twice replaces the
    previous entry rather than raising, so re-importing a provider
    module during development (or a plugin reloading itself) is never
    an error."""
    if not provider.provider_id:
        raise ValueError("LibraryProvider subclass must set a non-empty provider_id")
    _REGISTRY[provider.provider_id] = provider


def get_provider(provider_id: str) -> Optional[LibraryProvider]:
    """Looks up a registered provider by id, or None if nothing with
    that id has been registered (e.g. the provider module was never
    imported). Callers should treat None as "not available" rather than
    an error -- matching how this app treats other optional/unconfigured
    features elsewhere (see settings_dialog.py's defaulted settings)."""
    return _REGISTRY.get(provider_id)


def available_providers() -> list[LibraryProvider]:
    """All currently-registered providers, in registration order. Empty
    by default (see __init__.py) until a concrete provider module is
    both implemented and explicitly imported/registered -- this package
    existing does not, by itself, add any provider."""
    return list(_REGISTRY.values())


def unregister_all() -> None:
    """Clears the registry. Not used by app startup; exists for test
    isolation, so tests that register a fake provider don't leak it into
    other tests running in the same process."""
    _REGISTRY.clear()
