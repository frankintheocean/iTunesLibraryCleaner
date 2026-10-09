# 🎵 iTunes Manager 4.0.0

A major update focused on browsing the full library, richer collection statistics, safer playlist controls, and a complete history/field-journal clear operation—while retaining the existing library-cleaning, metadata and Last.fm functionality.

## 🐛 Fixes

- **Clear history also clears the Field journal.** The operation history and metadata-edit journal entries are removed together. Undo previews depending on cleared field-journal records are no longer available.
- **Correct album counts.** Album totals count distinct named album/album-artist pairs, not individual tracks. Empty and unknown-album placeholders are excluded.
- **Version consistency.** App, backend health and installer filenames now use version 4.0.0.

## 📚 Current Library

- New **Current Library** workspace showing song name, artist, album, genre and track length, with the same per-track artwork loader used elsewhere in the app.
- Sort each column in ascending or descending order; search the current library, select individual tracks, Shift-click a range, or use Ctrl+A / ⌘A to select all search matches.
- Copy selected songs to the app clipboard, paste them as a verified duplicate, duplicate selected songs, or delete them through an explicit confirmation and review step. Destructive live actions require a classic iTunes live-library profile; songs are backed up and verified before originals are removed from disk.
- **View Library** shortcut added beside **Find duplicates** on Overview.

## 📊 Overview and playlists

- New **Library Stats** widget highlights the top ten artists by available albums/tracks, five oldest and newest dated songs and albums, and five longest and shortest songs and albums with readable durations.
- Playlist picture uploads are saved and shown in the app immediately. The app also attempts a live iTunes playlist-artwork setter where the installed COM interface exposes one. Classic iTunes COM does not consistently document or expose playlist-art setters, so an unsupported setter is reported clearly and does not modify song artwork.
- Playlist reorder UI supports up/down buttons or drag-and-drop, selected in Settings. Smart, special, duplicate-entry and broken playlists are disabled. The documented classic iTunes COM interface does not expose a safe playlist-entry move API; if the installed interface cannot persist order, the queue reports the limitation without deleting or changing tracks. Use iTunes itself to reorder these playlists in the meantime.
- **Libraries** and **History** are accessible from **Settings**, rather than occupying permanent navigation slots.

## ♻️ Preserved from 3.1.1

- Existing library scanning, cleanup, metadata editing, duplicate discovery, playlists, file organization, consolidation, queue controls, verified copies, backups, restore manifests, and accessibility options remain available.
- Includes the current Last.fm image/profile fixes from the v3.1.1 repository branch.

## 📥 Windows downloads

The v4.0.0 release publishes these six assets, each with a SHA-256 sidecar:

- iTunes-Manager-4.0.0-win-x64.exe — Windows installer
- iTunes-Manager-4.0.0-win-x64.exe.sha256
- iTunes-Manager-4.0.0-package-win-x64.zip — portable Windows package
- iTunes-Manager-4.0.0-package-win-x64.zip.sha256
- iTunes-Manager-4.0.0-source.zip — source archive
- iTunes-Manager-4.0.0-source.zip.sha256

The installer is unsigned. Live iTunes COM actions require Windows and classic iTunes. Apple Music for Windows does not implement the same COM interface.
