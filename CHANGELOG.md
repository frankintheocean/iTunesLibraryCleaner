# 🗓️ iTunes Manager release history

## 🎵 3.1.1 — Pictures and scan timing

### 🐛 Fixes

- Fetch Last.fm pictures through safe CDN redirects, and read valid images even when the server labels them as binary files.
- Recover missing profile pictures and covers. Read artist photos from Last.fm’s public page when its API returns a placeholder.
- Retry missing pictures when you refresh. Use sharper profile thumbnails.
- Measure scan speed before estimating time left. Do not cap a large scan at the short default or borrow a tiny scan’s timing.
- Keep the saving phase clear until the library is ready.

### 🧭 Navigation

- Choose a library only in Overview. That selection stays active in every library tool.
- Keep library removal available in Libraries.

## 🎵 3.1.0 — Last.fm and large live scans

### 🐛 Fixes

- Keep a live scan running while it makes progress, even beyond 15 minutes. Stop stalled reads and keep cancel controls responsive.
- Explain read-only scan timeouts separately from uncertain metadata writes. Keep the write safeguards.
- Show the GitHub button only in Settings.

### 🎧 Listening

- Connect Last.fm with your own API key and username. Show a large profile picture and total plays.
- Browse recent songs and top songs, artists and albums. Choose all time, 7 days, 1 month, 3 months, 6 months or 1 year.
- Show available covers and artist photos, browse more results and refresh charts.
- Keep the API key out of UI responses and general preferences. Disconnect to remove it locally.

### 📍 Libraries

- Remove discovered locations from the suggestions without deleting files or unloading libraries.
- Restore hidden suggestions when needed.

## 🎵 3.0.0 — Faster libraries, safer live edits

### 🐛 Fixes

- Keep your selected library when background tasks finish, tabs change or another library opens.
- Count down the estimated time left. Show 100% only after all work and saving finish.
- Save new library copies without replacing XML files that Windows may have locked.
- Close database handles after each transaction to avoid lingering Windows locks.
- Find live songs by their exact iTunes ID when the direct lookup misses them. Name hints never replace the ID check.
- Retry temporary connection failures and refresh the iTunes connection while the app is open.
- Show a clear error when the service cannot return JSON.
- Use file sizes when an XML export leaves them out. Show “Unknown” for unavailable sizes instead of a misleading zero.
- Keep overview labels readable in every dark theme.

### ⚡ Faster work

- Parse large XML exports once, keep loaded copies ready and cache overview results.
- Index searches by text. Typing no longer reloads the overview and all playlists.
- Update only edited search rows after metadata changes.
- Read the real open iTunes library and reuse track IDs when reading playlist links. Check its identity before and after scanning.

### ✨ New tools

- Remove a library from its card or the library menu without deleting music or saved records.
- Clear the visible history while keeping undo and file restore records.
- Replace lasting success banners with notifications that disappear.
- Show whole-number genre percentages with song counts in brackets.
- Show playlist pictures from supported imported data, or choose a picture for the app.
- Set a default library XML path in Settings, including on another drive.

### 🎨 Appearance and downloads

- Use a new geometric music-library icon in ScoutTool’s mint, charcoal and amber style.
- Download an installer, a complete Windows app ZIP or a source ZIP, with checksums.
- Keep guides and release notes short, with helpful emoji groups.

## 🎵 2.0.0 — iTunes Manager

### 🐛 Fixes

- Scroll the tab heading and its content together. Song lists use the available window height.
- Keep the app name centered in the title bar.

### ✨ New tools

- Clear waiting and finished queue tasks while keeping active work and history safe.
- See live elapsed time and estimated time left under each task’s progress.
- Show available album covers in song lists, duplicate groups and playlist details.
- Choose the current live iTunes library from the library menu.
- Open the GitHub project from the button beside the library menu.

### 🎨 Appearance and accessibility

- Choose OLED Black, Ocean, Rose or Forest themes with black backgrounds and matching colors.
- Choose an interface font and adjust text from 25% to 400%, with a layout that adapts.
- Reduce animation, strengthen keyboard focus, enlarge click targets or underline links.

### 🛡️ Clearer choices

- Show simple emoji tooltips on actions that change or move your music.
- Show genre shares as percentages of the whole loaded library.
- Rename the app to iTunes Manager. Keep existing libraries, settings, history and backups in the same data folder.
- Use plain language and emoji groups for this and future release notes.


## 🎵 1.0 — Unified music-library app

- Edit genres, titles, artists, albums and other supported tags in live classic iTunes or media files.
- Review changes before applying them. Keep backups, field-by-field records and undo that preserves later edits.
- Browse libraries, clean genres, review duplicates, merge XML libraries and keep playlist links.
- Organize files with checked copies, collision protection, quarantine and restore records.
- Use an Apple-inspired interface with paged track tables, themes and native window controls.
- Open the original Cleaner and Consolidator for advanced workflows. Their original code and settings support remain available.
- Connect to Apple-distributed classic iTunes when running-object lookup fails. Real iTunes 12.13.11.1 source tests passed all 14 fields, separate readback and undo.
- Use the new flat record-and-note icon inspired by ScoutTool.
- Download a tested Windows installer or build a verified source ZIP. The installer is unsigned; installed-app live iTunes and further Windows 10/11 checks remain.

See [test results](docs/VALIDATION.md) and [known limits](docs/LIMITATIONS.md).

## 🏛️ Original release histories

[Cleaner](legacy/cleaner/CHANGELOG.md) · [Consolidator guide](legacy/consolidator/README.md). Consolidator’s in-app history remains in `legacy/consolidator/src/changelog.py`.
