# 📝 Release history

## 📦 🎵 1.0.0 — Current stable release

The [complete v1.0.0 notes](docs/RELEASE_1_0_0.md) group the current fixes and features with the work carried forward from pre-release 1.0, 2.0, 3.0, 3.1.0, and 3.1.1.

### 🐛 Key fixes
- 🧾 Clear History removes operation history and Field journal metadata edits together.
- 💿 Count distinct named albums instead of counting each track as an album.
- 🔎 Keep Current Library search focused, keep searches separate per tab, and prevent background polling from remounting the table.
- 📊 Return a consistent maximum of 100 rows for each Overview statistic, including duration lists.
- 🧩 Read Missing Tracks from the whole indexed library in batches without skipping tracks when the returned page is smaller.
- 🖼️ Make Last.fm image fetching more reliable and validate the generated matte Windows icon during packaging.

### ✨ Key additions
- 📚 Current Library table with artwork, sorting, search, range selection, copy, duplicate, paste, and guarded delete.
- 📊 Library Stats selector, Top 5 / 10 / 25 / 50 / 100, pagination, covers, and available artist portraits.
- 🧩 Missing Tracks view with album details and metadata-based gap detection.
- 🎨 App-side custom playlist pictures and safe playlist reordering when the live COM interface supports it.
- ⚙️ Workspace-tab visibility/order settings, plus accessibility, themes, and library/history shortcuts.
- 🎧 Last.fm listening charts and available profile, album, and artist pictures.
- 🛡️ Verified backups, previews, read-back checks, and refusal of unsupported risky live playlist operations.

### 📥 Release files
The v1.0.0 release publishes a Windows installer, portable Windows ZIP, source ZIP, and one SHA-256 file for each package. The installer is unsigned; live edits require classic iTunes on Windows.

## 📦 🎧 3.1.1 — Picture and scan timing improvements
- 🖼️ Follow safe Last.fm image redirects, accept valid images with generic content labels, retry missing pictures, use sharper profile thumbnails, and try public artist pages when API photos are missing.
- ⏱️ Estimate scan time from observed speed, keep the saving phase visible, and keep cancellation responsive.

## 📦 🚀 3.1.0 — Last.fm and large live scans
- 🎶 Add recent tracks and top tracks, artists, and albums across six time ranges, plus profile picture, total plays, and refresh/more controls.
- 🔗 Keep live scans moving beyond 15 minutes when progress continues; stop stalled reads and explain scan timeouts separately from uncertain writes.
- 🧭 Keep GitHub in Settings and let users hide or restore discovered library locations without deleting files.

## 📦 ⚡ 3.0.0 — Performance and safety
- 🧠 Parse large XML exports once, cache loaded copies and Overview results, index text searches, and update only changed rows after metadata edits.
- 🔒 Close database handles, avoid replacing locked XML exports, verify exact iTunes IDs and library identity, and retry temporary connection failures.
- 📈 Improve progress estimates, show unknown file sizes honestly, and make service JSON errors clearer.
- 🧹 Add library-profile removal, history controls, transient success notifications, improved genre percentages, default XML path settings, and playlist-picture display where supported.
- 📦 Add installer, portable ZIP, source ZIP, and checksum packaging.

## 📦 🎛️ 2.0.0 — Usability and accessibility
- 🧭 Improve tab/content scrolling, title-bar alignment, and song-list sizing.
- 🧰 Clear waiting/finished queue tasks safely and show elapsed time plus estimated time left.
- 🖼️ Show available covers in song lists, duplicate groups, and playlist details.
- 🌑 Add OLED Black, Ocean, Rose, and Forest themes; font selection, 25%–400% text sizing, reduced motion, stronger focus, larger click targets, and underlined links.
- 🛡️ Add emoji tooltips, whole-library genre percentages, and clearer app naming while preserving existing user data.

## 📦 🎵 1.0 — Unified music-library app
- ✍️ Edit supported tags in live classic iTunes or media files, with previews, backups, field journals, and guarded undo.
- 📚 Browse libraries, clean genres, review duplicates, merge XML libraries, manage playlist links, and organize files with collision protection, quarantine, and restore records.
- 🪟 Add the native desktop app, paged track tables, themes, and launchers for the original Cleaner and Consolidator.
- 🔗 Connect to Apple-distributed classic iTunes when running-object lookup fails; source-level tests checked 14 fields with read-back and undo on the tested version.

## 📦 🏛️ Original release histories
[Cleaner history](legacy/cleaner/CHANGELOG.md) · [Consolidator guide](legacy/consolidator/README.md). The Consolidator's in-app history remains in legacy/consolidator/src/changelog.py.
