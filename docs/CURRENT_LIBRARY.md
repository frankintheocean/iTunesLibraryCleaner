# 📚 Current Library

## 🔎 Browse

Open **Current Library** in the sidebar to list every song in the selected, scanned library. The table shows artwork, Song Name, Artist Name, Album Title, Genre, and Track Length. Use the column headings to sort ascending or descending, or search by song, artist, album, or genre. The search field sits below the row actions and above the headings. It retains focus while typing, and each workspace tab keeps its own search text when you switch away and back.

Artwork uses the same lazy track-art loader as other song lists. A missing cover displays the music icon; browsing never edits artwork. The table remains mounted while background job status refreshes, preventing routine polling from resetting the search field or flashing the rows.

## ✅ Select songs

- Click a song or checkbox to select one row.
- Hold **Shift** while selecting another row to select the range.
- Use **Ctrl+A** on Windows or **⌘A** on macOS to select all matches for the current search. If the search box is focused, the shortcut selects text instead.
- Use **Select all matches** to include every result, not just the visible page.

## 📋 Copy, paste, duplicate

**Copy selection** stores IDs in the app's clipboard. **Paste copy** creates new media files from that selection and asks live iTunes to import them. **Duplicate** uses the same verified-copy flow. These actions are available only for a live iTunes profile.

## 🗑️ Delete songs

Delete shows a warning before opening its review step. When confirmed and queued, the app rechecks each file signature, creates and verifies a safety copy, removes the song from the live iTunes library, then removes the original local file. Review the selected songs before confirming. Do not run destructive actions against a personal library before testing with backups.

## ⚠️ Limits

XML-import and folder profiles can be browsed, but live delete/duplicate actions need the matching classic iTunes library open on Windows. Apple Music for Windows does not expose the same COM API. Delete and duplicate actions scan the library again when completed so the visible list refreshes.
