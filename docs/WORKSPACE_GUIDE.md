# 🧭 Use the workspace

Choose a library, scan it, review proposed changes and confirm the ones you want. The workspace provides library cleanup, consolidation, duplicates, metadata, playlists and file organization, plus Queue, History and Settings.

## 🔎 Browse and scan

Track tables show pages of results, and search uses the saved database. Each library profile keeps its scan settings. Folder scans reuse unchanged tags. Scheduled scans run only while the app is open.

## ⏳ Manage work

Changes run one at a time. Pause and cancel take effect between tracks or files. Interrupted jobs show their saved progress after restart. If an edit only partly succeeds, make a new preview before retrying.

## 🛡️ Review changes

Live iTunes edits save a record for each field and check the result by reading it back. File-tag edits save verified backups. Duplicate merging creates a separate XML without deleting media. File transfers are checked before completion; moving files may require relinking them in iTunes.

## 🏛️ Use original tools

Settings can open the original Cleaner and Consolidator for advanced workflows, including cleanup presets, audio preview, restore points and rebuild/undo. Some original screens have no equivalent in the new interface. Keep their own confirmations and backups in mind.

## 🎨 Appearance

The app uses installed SF Pro fonts when available, with system fonts as a fallback. Apple fonts are not included. The new geometric music-library icon uses ScoutTool’s mint, charcoal and amber style with a distinct symbol.

## 🎵 Album covers and the current library

Song lists, duplicate groups and playlist details show album art when available. Covers come from local media or the live iTunes artwork collection. Missing or unreadable art uses a music icon. Artwork loading does not change songs.

When connected, choose **Current iTunes library** in the top-right library menu. The app scans the library that classic iTunes currently has open. Confirm live edits only after reviewing their previews. The connection refreshes while the app is open. Each live profile remembers which iTunes library it scanned; switching iTunes to another library requires adding that current library separately. An imported XML can edit live songs only when their exact IDs are present in the open iTunes library.

## ⏱️ Queue

Tasks show elapsed time and an estimated time left. The estimate counts down without increasing alongside elapsed time. It uses previous task times and progress, so it remains approximate. If it runs out before the task ends, the app says the task is taking longer. Only a fully finished task shows 100%. Pausing freezes active elapsed time. **Clear queue** cancels waiting tasks and hides finished tasks; running or paused work, saved history and undo records stay.

## ♿ Appearance and accessibility

Choose an OLED theme for a true-black page background with matching colors. Pick a font, adjust text from 25% to 400%, reduce motion, strengthen keyboard focus, enlarge controls or underline links. Text settings persist across restarts. Missing fonts use a system fallback. The GitHub button beside the library menu opens the project in your browser.

## 🗃️ Libraries and history

Loaded libraries stay ready when you change tabs or choose another saved collection. **Rescan** is an explicit refresh. Remove a library with the button beside the menu or **Remove** on its card. Finish or cancel its queued work first. Music, saved copies, backups and old change records stay; the profile is hidden and automatic scans stop.

**Clear history** hides the visible list. Field records and file restores remain below it, including preview buttons for undo. A later edit is preserved by undo checks.

## 🖼️ Playlist pictures

Pictures supplied in supported imported data appear across from the playlist name. Classic iTunes COM and standard XML exports do not expose its custom playlist pictures. Use **Choose picture** to select the same image for iTunes Manager; it does not change iTunes. Song album covers are separate.

## 📍 Default XML

In Settings, choose or enter **Default XML path**, then save it. That location appears first under **Discovered locations**, including when it is on another drive. A missing drive is reported as not found; it does not replace a loaded library.

## 🎧 Last.fm

Connect an API key and username to browse recent plays and top songs, artists and albums. Pick a time period and refresh when needed. The profile picture appears when Last.fm provides it. See the [Last.fm guide](LASTFM.md).

## 📍 Discovered locations

In Libraries, **Remove** hides a discovered suggestion. It does not delete its file or remove a loaded library. **Restore suggestions** shows hidden paths again. To remove a loaded library, use its separate Remove button.

## ⏳ Large live scans

A live iTunes scan can continue beyond 15 minutes while songs or playlist links are being read. If no forward progress arrives for 15 minutes, or the scan reaches six hours, it stops and keeps the previous saved copy. Check iTunes for an open dialog before retrying. Reading does not change live metadata. Queue’s cancel control stops a slow read without publishing an incomplete scan.
