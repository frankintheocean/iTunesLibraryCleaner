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
- Add Library Stats between Genre Mix and Library Health with top 10 artists by distinct available albums, oldest/newest top-five song and album release dates, and longest/shortest top-five songs and albums with readable durations.
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


## 🩹 1.0.0 hotfixes (same version)

These are maintenance fixes to the existing 1.0.0 release; the version number intentionally remains **1.0.0**.

- 🧭 Stabilize Current Library layout measurement to reduce recurring flicker.
- 🔎 Move Current Library search below the row-action buttons and above the column headings, keep song artwork and song text left-aligned, and clear search state when switching tabs so separate screens do not inherit another tab's query.
- ⌨️ Debounce search input slightly to avoid excessive rapid refreshes while typing.
- 📊 Replace the all-at-once Library Stats wall with a stat selector, configurable Top 5 / 10 / 25 / 50 / 100 display, and pagination.
- 🧩 Add a Missing Tracks workspace that groups indexed albums and highlights missing track numbers when track-count metadata is present.

**Notes:** Missing Tracks relies on track-number and track-count metadata from the loaded library; it cannot infer tracks absent from the source metadata. Playlist-image synchronization, customizable tab ordering/visibility, artist-photo sourcing, and the refreshed Apple-style application icon still require additional implementation and validation before they can be claimed as delivered.
