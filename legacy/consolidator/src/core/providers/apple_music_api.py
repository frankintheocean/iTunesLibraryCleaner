"""
Apple Music API provider -- SKELETON, not yet a working integration.

This module exists to demonstrate/anchor the provider plugin architecture
(see providers/base.py) for a specific real-world integration, and to give
a concrete starting point for implementing one. It is intentionally NOT
imported or registered anywhere in the app yet (see core/providers/__init__.py
and ui code -- neither imports this module), so its presence changes no
existing behavior.

What a real implementation would still need, not attempted here:
  - MusicKit/Apple Music API authentication (a developer token signed with
    an Apple-issued private key, plus a per-user music-user-token obtained
    through Apple's own auth flow) -- this is a meaningful chunk of
    service-specific auth work, not something to stub convincingly.
  - An HTTP client. Deliberately not importing `requests` or anything
    else here (see providers/base.py's "no new required dependency"
    design goal) -- a real implementation should add whatever HTTP
    dependency it needs at that point, in this module only, so the rest
    of the app is unaffected until this provider is actually enabled.
  - Rate limiting / pagination handling for the catalog and library
    endpoints.

The methods below raise ProviderError with a clear "not implemented yet"
message rather than pretending to work, so calling this in its current
state fails loudly and immediately instead of silently returning nothing
or partially-wrong data.
"""

from __future__ import annotations

from typing import Any, Iterable

from .base import (
    LibraryProvider,
    ProviderCapability,
    ProviderError,
    ProviderPlaylist,
    ProviderTrack,
)


class AppleMusicAPIProvider(LibraryProvider):
    """Placeholder for a future Apple Music API integration.

    Not registered by default -- a real implementation should call
    `register_provider(AppleMusicAPIProvider())` (see providers/__init__.py's
    docstring for the pattern) once the methods below are actually
    implemented, so the app's provider list only ever offers integrations
    that genuinely work.
    """

    provider_id = "apple_music_api"
    display_name = "Apple Music (API)"
    capabilities = frozenset({
        ProviderCapability.IMPORT,
        ProviderCapability.EXPORT,
        ProviderCapability.REQUIRES_AUTH,
    })

    def __init__(self, developer_token: str | None = None, music_user_token: str | None = None) -> None:
        # Tokens are accepted here (rather than read from e.g. an env var
        # internally) so the UI/settings layer stays in control of where
        # credentials come from and how they're stored -- this class
        # never reads app settings or the filesystem directly.
        self._developer_token = developer_token
        self._music_user_token = music_user_token

    def validate_source(self, source: Any) -> str | None:
        if not self._developer_token or not self._music_user_token:
            return "Apple Music API requires signing in before importing/exporting."
        return None

    def import_tracks(self, source: Any) -> Iterable[ProviderTrack]:
        raise ProviderError(
            "Apple Music API import is not implemented yet. This provider "
            "is a skeleton for future work -- see "
            "core/providers/apple_music_api.py."
        )

    def import_playlists(self, source: Any) -> Iterable[ProviderPlaylist]:
        raise ProviderError(
            "Apple Music API playlist import is not implemented yet. See "
            "core/providers/apple_music_api.py."
        )

    def export_tracks(self, tracks: Iterable[ProviderTrack], destination: Any) -> None:
        raise ProviderError(
            "Apple Music API export is not implemented yet. See "
            "core/providers/apple_music_api.py."
        )
