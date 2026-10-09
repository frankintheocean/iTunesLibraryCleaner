# 🎼 Current Library guide

Current Library lists every song in the selected, scanned library. Artwork uses the same shared loader as File Organizer.

## 🔎 Browse and sort
Search the library, then select a column heading to sort ascending. Select it again to reverse the sort. The columns are Song Name, Artist Name, Album Title, Genre, and Track Length.

## ☑️ Select songs
- Click a checkbox to select one song.
- Shift-click to select a range.
- Use Ctrl+A on Windows or ⌘A on macOS to select all songs matching the search.
- Use Copy selection or Ctrl+C to save selected track IDs to the app's clipboard. This does not copy audio bytes to the system clipboard.

## 📋 Duplicate or paste
Choose Duplicate or Paste copy to review the operation. The app creates collision-safe file copies, verifies their SHA-256 hashes, then requests import into live iTunes. Existing files are not overwritten.

## 🗑️ Delete safely
Delete prompts for confirmation and then a review step. The action requires a live classic iTunes profile, local unprotected audio, and a unique file reference. A verified recovery copy is created before iTunes and disk deletion. Protected files, shared file references, and files changed since preview are refused.

## 🎵 Playlist order
In Settings, choose Up and down buttons or Drag and drop. The selected live iTunes profile must contain a regular playlist; smart and built-in playlists cannot be reordered. Set iTunes to **View → Sort By → Playlist Order** first. The task verifies the requested order and attempts to restore the old order if iTunes refuses the change.

## ⚠️ Compatibility
XML and folder profiles are read-only for live delete/duplicate actions. Windows and classic iTunes are required for COM tasks; Apple Music for Windows does not provide the same interface. After a successful live change, the app rescans to refresh the Current Library view.
