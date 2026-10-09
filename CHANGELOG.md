# Changelog

## 1.0 — Unified workspace

- Support Apple-distributed classic iTunes when the running-object lookup fails: use the original Cleaner’s Dispatch activation for MK_E_UNAVAILABLE. Other COM errors remain explicit.
- Real iTunes 12.13.11.1 source validation reported PASS for all 14 live metadata fields, independent readback and conditional undo.
- Replace the glossy disc icon with a flat dark-tile music symbol, mint geometry and an orange accent inspired by the supplied ScoutTool style.

- Added React/TypeScript/Electron desktop shell with Apple-inspired light/dark and color themes, virtualized track pages, native window controls and original icon assets.
- Preserved both original applications, algorithms, settings paths and advanced legacy interfaces.
- Added shared live iTunes COM editing for genre, title, artist, album, album artist, year, track/disc numbering, composer, comments, compilation and rating.
- Added field-level write journals, readback, conditional undo previews and explicit partial-failure reporting.
- Added library profiles, streaming XML import, folder metadata caching, duplicate review and playlist-preserving XML merge exports.
- Added verified file transfers, organization templates, quarantine/restore manifests, tag backups, playlist migration exports and persistent queue/history.
- Added reproducible source packaging and Windows bundling/NSIS tooling. Windows release validation remains required.

## Original release histories

LibraryCleaner 3.0 history: `legacy/cleaner/CHANGELOG.md`.
Consolidator 2.2 and earlier history: `legacy/consolidator/src/changelog.py` and its README.
