# 🧭 Use the workspace

Choose a library, scan it, preview changes, then confirm. The app includes cleanup, consolidation, duplicates, metadata, playlists, file organization, Current Library, Queue, and Settings.

## 📚 Browse and scan

Choose the active library in **Overview**. Track pages and searches use the saved SQLite index. **Current Library** shows every indexed song with art and sortable columns. Shift-click selects a range; Ctrl+A / ⌘A selects every match.

## ⏳ Manage work

Jobs run one at a time. Queue shows progress, elapsed time, and an approximate time left. Pause/cancel apply between safe work units. Interrupted work is shown after restart; create a fresh preview before retrying a partially completed edit.

## 🛡️ Review edits

Live iTunes changes use persistent IDs, field journal records, and read-back checks. File-tag changes keep verified backups. Moving files can require relinking. Duplicate merge exports create a separate XML and do not delete songs.

## 📊 Overview

Album counts group tracks by named album and album artist. **Library Stats** highlights top artists with available albums, oldest/newest dated songs and albums, and longest/shortest song and album durations. Dates or durations missing from the source tags are omitted from the corresponding lists.

## 🎨 Appearance and accessibility

Settings includes themes, fonts, text size, reduced motion, stronger keyboard focus, larger click targets, and link styling. SF Pro is used only if installed; system fonts are fallbacks. Apple fonts are not bundled.

## 🗂️ Libraries and history

Open **Settings → Manage libraries** to add, scan, configure, or remove profiles. Removing a profile does not delete its media files or saved backups.

Open **Settings → History & Field journal** to review operation results and metadata-edit entries. **Clear history** permanently clears both operation history and Field journal entries. Metadata edits represented by cleared entries can no longer be undone through this app. Existing safety copies and transfer manifests remain separate.

## 🖼️ Playlist pictures and order

Playlist pictures save in iTunes Manager immediately. The app attempts live application if the installed classic iTunes COM interface exposes a playlist-art setter; otherwise the app keeps the picture locally and reports the limitation. Song artwork is not changed as a fallback.

For a regular live iTunes playlist, choose **Up and down buttons** or **Drag and drop** in Settings. A live reorder is accepted only if COM exposes a playlist-only move method and the app can verify the resulting order. Smart playlists, special playlists, broken lists, and repeated entries are blocked. Unsupported versions report that nothing was changed.

## 🎧 Last.fm and paths

Last.fm uses your own API key and username to show recent plays and top charts; it does not scrobble or edit the account. In Settings, set **Default library XML** to prioritize a library export. Hidden discovered locations can be restored without changing files.

## ⚡ Large scans

A live iTunes scan can take longer than 15 minutes. If forward progress stops for 15 minutes, or the scan reaches six hours, it stops and keeps the previous snapshot. Check iTunes for a modal dialog before retrying.
