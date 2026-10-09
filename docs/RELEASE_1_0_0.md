# 🎵 iTunes Manager 1.0.0

A major update focused on browsing the full library, richer collection statistics, safer playlist controls, and clearing the complete history journal—while retaining the existing library-cleaning and Last.fm features.

## 🐛 Fixes
- Fix **Clear history** so it removes Field journal metadata-edit entries as well as operation history. Clearing the journal also removes those app-side undo references.
- Correct album totals by counting distinct named albums per album artist/title instead of counting each track as an album. Unknown and untitled placeholders are excluded.
- Keep product, backend-health, and installer versions aligned at 1.0.0.

## 📚 Current Library
- Browse every indexed song with album artwork, song name, artist name, album title, genre and track length.
- Sort each column in ascending or descending order; search; select rows, Shift-click ranges, or select all matches with Ctrl+A / ⌘A.
- Copy a selection within the app, duplicate tracks, paste a copied selection as new local media files, or delete songs from live iTunes and disk. Deletions use confirmation, review, signature checks and verified safety copies. Library write actions require live classic iTunes.

## 📊 Overview and playlists
- Add Library Stats between Genre Mix and Library Health, with a statistic selector, Top 5 / 10 / 25 / 50 / 100 result limits, pagination, available song/album artwork, and Last.fm artist portraits where configured.
- Add the **View library** shortcut beside **Find duplicates**.
- Move the Libraries and History screens into Settings' Library shortcuts.
- Choose up/down controls or drag-and-drop to reorder entries in regular playlists. The queued operation attempts a playlist-only move method when the installed COM interface exposes one, then verifies read-back. If no safe method is exposed, it refuses the reorder without deleting tracks or changing other playlists. Smart playlists, special/system playlists, and repeated entries are blocked for safety.
- Uploaded playlist covers appear immediately in the app. The app tries live playlist artwork only when the installed COM object exposes a setter; classic iTunes COM does not document playlist artwork writing, so unsupported versions keep the image in the app and report the limitation. Song artwork is never altered to simulate playlist artwork.

## ♻️ Carried forward
Existing library scanning, cleanup, consolidation, duplicate review, metadata editing, file organizing, task queue, backup and undo safety, themes/accessibility, and Last.fm charts and image fallbacks remain included. Existing per-user settings and data are preserved across upgrades.

## 📥 Downloads
- `iTunes-Manager-1.0.0-win-x64.exe` — Windows installer
- `iTunes-Manager-1.0.0-win-x64.exe.sha256` — installer SHA-256
- `iTunes-Manager-1.0.0-package-win-x64.zip` — portable Windows app
- `iTunes-Manager-1.0.0-package-win-x64.zip.sha256` — portable ZIP SHA-256
- `iTunes-Manager-1.0.0-source.zip` — source package
- `iTunes-Manager-1.0.0-source.zip.sha256` — source ZIP SHA-256

Requires Windows 10/11 x64 for the installer. Live iTunes editing requires classic iTunes on Windows; Apple Music for Windows does not expose the iTunes COM interface. The installer is unsigned. Automated fixture checks do not replace a manual check with the target Windows/iTunes version.


## 🧭 Included improvements from 3.1.0 and 3.1.1

### 🎧 Last.fm pictures and listening charts
- Follow safe redirects and read valid image responses even when servers label them as binary data.
- Retry missing profile pictures and covers on refresh, use sharper profile thumbnails, and read public artist photos when the API has no image.
- Browse recent tracks and top tracks, artists, and albums across the available listening periods. Last.fm remains read-only.

### ⏱️ More reliable library scans
- Keep large live scans moving beyond 15 minutes, stop stalled reads, and keep cancellation responsive.
- Estimate time remaining from observed scan speed rather than a short default or a tiny test scan.
- Show the saving phase until the library is ready, and distinguish read-only scan timeouts from uncertain metadata writes.

### 🧭 Clearer library navigation
- Choose the active library in Overview and keep that selection across library tools.
- Keep library removal available in Libraries. Hidden discovered locations can be restored without deleting files or unloading libraries.
- Keep the GitHub link in Settings.


## 🩹 1.0.0 maintenance and feature polish

These changes keep the published product version at **1.0.0**.

- 🧭 Keep Current Library layout stable across background polling so the table does not repeatedly unmount.
- 🔎 Keep search text independent for each workspace tab, preserve keyboard focus while typing, and place Current Library search beneath the action controls and above the column headings.
- 🎵 Keep song artwork and song text left-aligned in Current Library; use lazy artwork loading for large libraries.
- 📊 Add Library Stats selection, Top 5 / 10 / 25 / 50 / 100 limits, pagination, cover thumbnails, and Last.fm artist portraits where available.
- 🧩 Add Missing Tracks, loading the entire indexed library in pages rather than treating the current visible page as the full collection. Album track gaps are inferred from track-number and track-count metadata when that metadata exists; tracks absent from both the index and its metadata cannot be inferred reliably.
- 🖼️ Allow a user-selected picture for each playlist. The app saves and displays that picture; live iTunes synchronization is attempted only when the installed COM interface supports it.
- 🧭 Let users hide/show and reorder workspace tabs in Settings, with those preferences saved.
- 🎨 Use a flat, matte OLED-black app mark and regenerate/validate the native Windows icon from the icon source during Windows packaging.
- 🗂️ Keep the repository path guide emoji-led, concise, and specific to each tracked path.

## 🏷️ File and folder description style

Use a leading emoji and concise, everyday wording for each tracked path. Prefer a distinct emoji per path and avoid repeating descriptions. Keep labels factual, including Windows/iTunes COM or Last.fm setup requirements where those affect availability. Update the path index when paths are added, renamed, or removed.
