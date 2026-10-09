# 🎵 iTunes Manager 4.0.0

A major release focused on a full-library browser, richer collection statistics, verified song actions, playlist ordering controls, and a complete History/Field journal clear action.

## 🐛 Fixes
- **Clear History clears Field journal entries too.** History and metadata edit rows are deleted together. Cleared edits can no longer be used for undo in this app.
- **Correct album totals.** An album is counted once per album artist and album title, rather than once per song. Blank and unknown album placeholders are excluded.
- **Version consistency.** UI, backend health checks, installer, portable package, source ZIP, and checksums use version 4.0.0.

## ✨ What's new
- **Current Library:** browse every song with artwork, sortable columns, search, Shift-click range selection, Ctrl+A / ⌘A, copy/paste selection, duplicate, and delete.
- **Library Stats:** top ten artists by albums with available tracks, top five oldest/newest songs and albums, and top five longest/shortest songs and albums with readable durations.
- **View Library:** new Overview shortcut beside Find duplicates.
- **Playlist order:** choose up/down buttons or drag-and-drop in Settings. Changes go through the review/queue path and are applied to user-playlist entries only; the main library tracks and media files are never deleted as a reorder shortcut.
- **Simpler navigation:** Libraries and History live under Settings.
- **Retained functionality:** metadata editing, library scanning, duplicate discovery, genre cleanup, organization/consolidation, history reporting, accessibility, and Last.fm picture fixes remain.

## 🛡️ Safety and known limits
Delete and duplicate actions require Windows, classic iTunes, and a live library profile. Originals are backed up and verified before delete. Protected media and media paths shared by multiple library entries are refused. Playlist reordering is restricted to regular playlists, requires **View → Sort By → Playlist Order** in iTunes, verifies the result and attempts rollback if iTunes refuses the order. Smart and built-in playlists are not reorderable here. The installer is unsigned.

## 📥 Version 4.0.0 Windows release files
The release workflow creates all six assets only after its Windows build and installer-validation steps pass:

- `iTunes-Manager-4.0.0-win-x64.exe` — Windows installer
- `iTunes-Manager-4.0.0-win-x64.exe.sha256` — installer checksum
- `iTunes-Manager-4.0.0-package-win-x64.zip` — portable package
- `iTunes-Manager-4.0.0-package-win-x64.zip.sha256` — package checksum
- `iTunes-Manager-4.0.0-source.zip` — source archive
- `iTunes-Manager-4.0.0-source.zip.sha256` — source checksum

See [Current Library](CURRENT_LIBRARY.md), [validation evidence](VALIDATION.md), and [known limitations](LIMITATIONS.md) before destructive operations.
