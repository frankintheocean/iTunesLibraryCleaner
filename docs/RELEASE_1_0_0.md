# 🎵 iTunes Manager 1.0.0

A consolidated record of the current 1.0.0 build. These notes include current changes plus work carried forward from pre-release 1.0, 2.0, 3.0, 3.1.0, and 3.1.1. Version labels and published asset names stay at **1.0.0**.

## 🐛 Fixes and reliability

- 🧾 **Clear History** removes operation history and Field journal metadata-edit entries together. Cleared entries no longer provide in-app undo references.
- 💿 Count distinct named albums by album artist and album title, not by song. Ignore empty, unknown, and untitled placeholders.
- 🔎 Keep search focus while typing, preserve separate search text for each workspace tab, and stop background polling from remounting or flashing the Current Library table.
- 📊 Cap every Overview statistic at 100 results, including duration-based lists, so Top 5 / 10 / 25 / 50 / 100 and paging behave consistently.
- ⏱️ Let live scans continue while progress is being made, including scans longer than 15 minutes. Stop stalled reads and keep cancellation responsive.
- 🧮 Estimate time remaining from measured scan speed instead of a short default or a tiny test scan. Keep the saving phase visible until the library is ready.
- 🗃️ Close database handles after transactions, avoid replacing locked XML exports, and retry temporary iTunes connection failures while the app is open.
- 🪪 Match live songs by exact iTunes ID. Name hints never replace ID verification, and check library identity before and after scans.
- 📦 Use file sizes when available; show “Unknown” instead of a misleading zero when size data is missing.
- 🧯 Show a clear error when the local service cannot return valid JSON. Separate read-only scan timeouts from uncertain metadata-write outcomes.
- 🖼️ Follow safe image redirects, accept valid image bytes when servers label them as generic binary data, retry missing covers on refresh, and use sharper profile thumbnails.
- 🎤 When Last.fm's API has no artist photo, try its public artist page. Pictures can still be unavailable if the site blocks access or changes.
- 🧩 Keep the native Windows icon in sync with the matte OLED-black icon source and validate the generated ICO at multiple sizes during packaging.
- 🏷️ Keep the app, backend-health response, installer, and release labels aligned at 1.0.0.

## 📚 Library browsing and navigation

- 🎵 Browse every indexed song in **Current Library**, with artwork, song, artist, album, genre, and length columns.
- ↕️ Sort each column in either direction; search by song, artist, album, or genre; select one row, Shift-click a range, or select all matches with Ctrl+A / ⌘A.
- 📋 Copy a selection inside the app, duplicate tracks, paste a copied selection as new local media files, or delete selected songs from live iTunes and disk.
- 🛡️ Review destructive actions before confirming. Delete rechecks file signatures and makes verified safety copies before removing the original. Write actions require the matching live classic iTunes library.
- 🧭 Add **View library** beside **Find duplicates** and keep the selected library consistent across library tools.
- 🗃️ Move Libraries and History to Settings shortcuts. Remove discovered locations from suggestions without deleting media or unloading a library; restore hidden suggestions when needed.
- 🎛️ Keep the GitHub project link in Settings and keep the active library selector in Overview.

## 🧩 Missing Tracks

- 💽 Add a dedicated view for albums with likely gaps, showing available album art, metadata, tracks present, and inferred missing track numbers.
- 📚 Read the full indexed library in batches rather than treating the visible Current Library page as the whole collection.
- 🔢 Advance pagination by the actual returned batch size so smaller backend pages do not skip tracks.
- ⚠️ Detection depends on track number and track-count metadata. If the source data does not describe a track or expected album length, the app cannot reliably infer that gap.

## 📊 Overview and statistics

- 📈 Add **Library Stats** between Genre Mix and Library Health.
- 🎚️ Choose a statistic and display Top 5, 10, 25, 50, or 100 results; page through the returned results.
- 🎨 Show available song and album artwork, plus Last.fm artist portraits when a configured connection provides them.
- 🗓️ Show artists with the most distinct albums, oldest and newest songs/albums with known years, and longest and shortest songs/albums with readable durations.
- 🧮 Show whole-number genre percentages with song counts, and keep Overview labels readable across dark themes.

## 🎧 Playlists and pictures

- ↕️ Reorder regular playlists with up/down controls or drag-and-drop, using the mode chosen in Settings.
- 🔒 Apply a live reorder only when classic iTunes COM exposes a safe playlist-only move method; verify the result by reading the order back.
- 🚫 Refuse unsupported interfaces, smart/system playlists, and repeated-entry playlists rather than risking track deletion or changing another playlist.
- 🖼️ Choose a custom picture for each playlist. The app saves and displays it immediately; live iTunes writing is attempted only when a compatible artwork setter exists. Song artwork is never altered as a substitute.

## ✍️ Tags, cleanup, and file safety

- 🏷️ Edit supported genres, titles, artists, albums, and other tags in live classic iTunes or media files.
- 👀 Preview changes before applying them. Keep field-by-field journal records, verified file backups, undo checks, and safety copies for destructive file operations.
- 🧹 Keep genre cleanup, split-album review, duplicate review, consolidation, library merging, file organization, quarantine/restore records, and task queue/history.
- 📂 Protect against filename collisions and unsafe shared/protected files. Moving files can break iTunes references; use export/import/relink steps where needed.
- 🏛️ Keep the original Cleaner and Consolidator tools and their existing workflows available for advanced options that have not been rebuilt in the new interface.

## 🎧 Last.fm listening

- 🔑 Connect using your own API key and username. The connection is optional, read-only, and requires internet access.
- 🎶 Browse recent tracks and top tracks, artists, and albums for all time, 7 days, 1 month, 3 months, 6 months, or 1 year.
- 🖼️ View available profile pictures, covers, and artist photos; browse more results and refresh charts.
- 🔐 Keep the API key out of general UI responses and preferences. Disconnect to remove it locally. Private-data access and scrobbling are not supported.

## ⚙️ Settings, appearance, and accessibility

- 🧭 Show or hide workspace tabs and change their order; save those preferences.
- 🎨 Choose OLED Black, Ocean, Rose, or Forest themes.
- 🔤 Choose an interface font and adjust text from 25% to 400%; use reduced motion, stronger keyboard focus, larger click targets, or underlined links.
- 🪟 Keep the app name centered in the title bar, scroll tab headings and content together, and size song lists to the available window height.
- 🔔 Use short notifications instead of permanent success banners. Clear waiting/finished queue tasks without removing active work or history, and show elapsed time plus estimated time remaining.
- 💾 Preserve existing user libraries, settings, history, and backups across upgrades.

## ⚡ Speed and scanning improvements carried forward

- 🗃️ Parse large XML exports once, keep loaded copies ready, cache Overview results, and index text searches.
- 🪶 Update only edited search rows after metadata changes rather than reloading every Overview and playlist.
- 🔗 Read the real open iTunes library and reuse track IDs when reading playlist links; verify library identity before and after scanning.
- 🧮 Use observed progress for scan estimates. A scan stops after 15 minutes without forward progress or after the six-hour overall limit; metadata-write deadlines are unchanged.
- 🧪 The extended deadline has simulated tests with 48,000 generated track IDs, but a fresh large-library scan against real classic iTunes still needs user validation.

## 🏛️ Earlier pre-release work included in 1.0.0

### 🎵 Pre-release 1.0 — Unified music-library app
- ✍️ Edit supported tags in live classic iTunes or media files, review changes first, keep backups, record field changes, and undo when values still match the app's last write.
- 📚 Browse libraries, clean genres, review duplicates, merge XML libraries, and keep playlist links.
- 🗂️ Organize files with checked copies, collision protection, quarantine, and restore records.
- 🪟 Use a native desktop window, paged track tables, themes, and the original Cleaner/Consolidator launchers.
- 🔗 Connect to Apple-distributed classic iTunes when running-object lookup fails; source-level checks passed all 14 fields with read-back and undo on the tested iTunes version.

### 🎛️ Pre-release 2.0 — Usability and accessibility
- 🧭 Scroll tab headings and content together, center the title-bar app name, and fit song lists to the available height.
- 🧰 Clear waiting and finished queue tasks while keeping active work and history safe.
- ⏳ Show live elapsed time and estimated time left for each task.
- 🖼️ Display available album covers in song lists, duplicate groups, and playlist details; choose a current live iTunes library from the library menu.
- 🌑 Add OLED Black, Ocean, Rose, and Forest themes, font choice, 25%–400% text sizing, reduced motion, stronger focus, larger click targets, and underlined links.
- 🛡️ Add plain-language emoji tooltips to actions that move or change music, and show genre shares as percentages of the whole loaded library.

### 🚀 Pre-release 3.0 — Performance and safety
- 🧠 Reduce repeated parsing and ID lookups, cache loaded XML and Overview results, and index search text.
- 🔄 Keep the selected library stable across background tasks, tab changes, and library opens.
- 📉 Show countdown estimates and only report 100% when work and saving are complete.
- 🔒 Avoid replacing locked XML files and close database handles after transactions.
- 🧾 Use exact iTunes IDs, retry temporary connections, check library identity, and report missing size data honestly.
- 🧹 Remove a library profile without deleting its music or saved records; clear visible history while preserving undo/file-restore records in that earlier workflow.
- 🎨 Add the first generated music-library icon, installer/portable/source packages, and checksum files.

### 🎧 Pre-release 3.1.0 and 3.1.1 — Last.fm pictures and long scans
- 🎤 Show a large Last.fm profile picture and total plays, recent tracks, and top tracks/artists/albums over six listening periods.
- 🖼️ Add profile, album, and artist pictures, more-results browsing, and refresh controls.
- 🧭 Keep library removal in Libraries, restore hidden discovered locations, and keep GitHub in Settings.
- ⏱️ Keep progressing live scans running beyond 15 minutes, stop stalled reads, and keep cancellation responsive.
- 🧮 Improve time-left estimates using observed scan speed and keep the saving phase visible until ready.
- 🪄 Follow safe Last.fm image redirects, accept valid image data despite generic server labels, retry missing pictures, and use public artist pages when the API has no photo.

## 📥 Downloads

The published v1.0.0 release contains these six assets:

- **iTunes-Manager-1.0.0-win-x64.exe** — Windows installer
- **iTunes-Manager-1.0.0-win-x64.exe.sha256** — installer SHA-256
- **iTunes-Manager-1.0.0-package-win-x64.zip** — portable Windows app
- **iTunes-Manager-1.0.0-package-win-x64.zip.sha256** — portable ZIP SHA-256
- **iTunes-Manager-1.0.0-source.zip** — source package
- **iTunes-Manager-1.0.0-source.zip.sha256** — source ZIP SHA-256

Requires Windows 10/11 x64 for the installer. The installer is unsigned. Live iTunes editing requires classic iTunes on Windows; Apple Music for Windows does not expose the required COM interface. Automated checks do not replace manual tests with the target Windows/iTunes version.

## 🏷️ Documentation style

Use plain, everyday wording and emoji-led category headings. Keep each bullet short and factual, avoid repeating descriptions, and state known limits beside the feature they affect. Keep [the repository path guide](REPOSITORY_LABELS.md) current whenever tracked paths change.
