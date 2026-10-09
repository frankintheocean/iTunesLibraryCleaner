# 🎵 iTunes Manager 4.0.0

A local Windows desktop app for browsing, cleaning, and editing music libraries. Your library stays on your device.

## ✨ What you can do

- 📚 **Current Library:** browse every indexed song with artwork, sort by name, artist, album, genre, or length, and select rows individually, by Shift-click range, or with Ctrl+A / ⌘A.
- 📊 **Overview:** see distinct album counts, Genre Mix, Library Stats, and Library Health.
- 🎧 **Playlists:** choose up/down buttons or drag-and-drop for reorder controls. A live reorder is applied only if the running classic iTunes COM interface exposes a safe move method. Unsupported versions refuse the change without deleting tracks.
- ✍️ **Metadata:** preview and confirm live iTunes edits or backed-up file-tag edits.
- 🧹 **Cleanup:** inspect genres, split albums, duplicates, and file organization.
- 🧰 **Queue & history:** watch jobs and review outcomes. Clear history also removes Field journal entries, so cleared metadata edits can no longer be undone in the app.
- ⚙️ **Settings:** manage library profiles, history, accessibility, themes, genre rules, and playlist reorder controls.
- 🎨 **Playlist pictures:** save artwork in iTunes Manager and attempt to apply it to live iTunes where the COM interface permits. Song artwork is never used as a playlist-art fallback.
- 🎧 **Last.fm:** browse listening charts and available profile, artist, album, and track pictures.

## 📥 Install

Get the **installer**, **portable Windows ZIP**, or **source ZIP** from [GitHub Releases](https://github.com/frankintheocean/iTunesLibraryCleaner/releases/tag/v4.0.0). Extract the whole portable ZIP before opening `iTunes Manager.exe`. The installer is unsigned. Live editing requires Windows and **classic iTunes**—Apple Music for Windows does not provide this COM interface.

## 🛠️ Run from source

Use Python 3.12 and Node 22.12 or later. From the repository root:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-lock-windows.txt
npm ci
npm run build
npm run desktop
```

For the Windows installer and full validation, use `scripts/build-windows.ps1` on Windows. See [build notes](BUILD.md), [test guide](TESTING.md), and [validation evidence](docs/VALIDATION.md).

## 🛡️ Safety notes

Review every preview before confirming. Delete and duplicate actions in Current Library require confirmation; delete makes and verifies a safety copy before removing the original file. Clearing the Field journal removes app-side undo references. Playlist operations refuse unsafe COM workarounds. Backups and transfer manifests are stored separately.

## 🗂️ Project map

See the [file and folder guide](docs/REPOSITORY_LABELS.md), [workspace guide](docs/WORKSPACE_GUIDE.md), [known limits](docs/LIMITATIONS.md), [Last.fm guide](docs/LASTFM.md), and [release notes](docs/RELEASE_4_0_0.md). Third-party license notices remain in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
