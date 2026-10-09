# Unified iTunes Library Manager 4.0.0

A Windows desktop music-library workspace combining LibraryCleaner and iTunes Library Consolidator, with a React interface and Python services. This is a source release with Linux validation; a validated Windows installer is not included.

The **live iTunes** target writes directly through classic iTunes' Windows COM API. Genre cleanup, split-album merging and the metadata editor share one writer. Supported live fields: genre, song title, artist, album, album artist, year, track/disc numbers and counts, composer, comments, compilation and rating. COM uses genuine persistent IDs, signed 32-bit halves, an isolated initialized apartment, reconnects on rejected calls, per-field journals and readback. Editing an XML alone is never represented as editing live iTunes.

The **file tags** target uses Mutagen and saves verified full-file backups before editing. Every mutation is previewed and explicitly confirmed. Duplicate consolidation writes a separate XML and repoints playlist entries using the original merge algorithm; it does not delete physical media. File consolidation uses hash-verified staging and exclusive atomic publication. Moving/quarantining files can break live references; a separate relink workflow/export is supplied.

## Running from source

Requires Python 3.12+, Node 22.12+, and Windows 10/11 x64 for live iTunes. Open classic iTunes before connecting. Apple Music for Windows does not expose this COM interface.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-lock-windows.txt
npm ci
npm run build
npm run desktop
```

Linux development and domain/API tests are supported using `requirements-lock-linux.txt`; live COM and Windows packaging need Windows. Electron needs an available graphical display. See [BUILD.md](BUILD.md).

## Workspace

Overview, Libraries, Library Cleaner, Consolidation, Duplicates, Metadata, Playlists, File Organizer, Queue, History and Settings are connected to backend operations. Track tables virtualize pages of 500 rows and allow navigation through the entire library. Search runs against SQLite. Profiles retain independent source and scan configuration. Folder scans reuse unchanged metadata; scheduled scans run only while the app is open. Jobs serialize mutations, pause/cancel between files/tracks, and expose interrupted checkpoints after restart. Metadata retries require a new preview if the previous result may be partial.

Settings opens the **preserved original Cleaner and Consolidator** interfaces for original workflows not redesigned into React (detailed cleanup presets/cache/notifications, advanced duplicate exclusions, audio preview, named restore points, growth trends and rebuild/undo). Their code and exact original themes remain available in writable user-data mirrors. This retention does not claim every legacy screen has a React replacement.

## Appearance

The UI requests installed SF Pro Display/Text first, then system fallbacks including Segoe UI. Apple font files and proprietary Apple icons are not distributed. An original stacked-record icon is supplied as PNG and a seven-resolution Windows ICO. Generated source artwork is retained in `resources/icon-source.png`.

## Safety and limitations

Read [docs/FEATURE_PARITY.md](docs/FEATURE_PARITY.md), [docs/VALIDATION.md](docs/VALIDATION.md) and [docs/LIMITATIONS.md](docs/LIMITATIONS.md) before using live operations. COM has no multi-property transaction: partial outcomes are recorded, not hidden. Live and file-tag undo apply only when the value still matches the previous write. Backups are retained, never pruned automatically by the unified services. Filesystems without hard-link publication fail safely; cross-filesystem copies stage on the destination volume. Proprietary ITL/Apple Music databases are not directly edited. DRM files are not modified or bypassed.

Original legacy tools retain their original potentially irreversible deletion/rebuild behavior. Use their confirmations and backups. No remote upload, Git push or publication is performed.

## Development

```sh
.venv/bin/python -m pytest tests legacy/consolidator/tests -q
npm test
npm run build
python3 scripts/package-source.py
```

See [ARCHITECTURE.md](ARCHITECTURE.md), [MIGRATION.md](MIGRATION.md), [TESTING.md](TESTING.md), [INSTALL.md](INSTALL.md) and [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

Windows preview installer: [download the executable](https://github.com/frankintheocean/iTunesLibraryCleaner/releases/download/v4.0.0-windows-preview/Unified-iTunes-Library-Manager-4.0.0-win-x64.exe). See the [release notes and checksum](https://github.com/frankintheocean/iTunesLibraryCleaner/releases/tag/v4.0.0-windows-preview). Real iTunes COM acceptance remains pending.
