# 📥 Install, repair, and remove

## 🚀 Install on Windows

Download the installer or portable app ZIP from [GitHub Releases](https://github.com/frankintheocean/iTunesLibraryCleaner/releases/tag/v1.0.0).

- **Installer:** choose a folder and create Start Menu/Desktop shortcuts.
- **Portable ZIP:** extract every file into one writable folder, then open `iTunes Manager.exe`. Keep its folders together.
- **Source ZIP:** contains source code, not a ready-to-run installer.

The app does not need Python or Node after installation. The installer is unsigned. Live iTunes editing needs Windows and classic iTunes.

## 🔧 Repair

Close iTunes Manager and both original tools, then run the installer for the same version again. App data stays in place.

You can also run `scripts/repair-windows.ps1 -InstallerPath <path>`. This opens the installer; it is not a separate MSI repair function.

## 🗑️ Uninstall

Windows removes the app, shortcuts, and registration. It keeps user data, music, exports, backups, and quarantined files.

Review the app-data folder before deleting it manually—it may contain media safety copies and restore manifests.

## 💾 Data and upgrades

By default, app data lives in the per-user **Unified iTunes Library Manager** folder under Windows AppData. The installer uses the same application ID and data location, so upgrading from v3.1.1 keeps saved libraries, settings, and backups. Close the old app before upgrading.

The portable ZIP also uses AppData for settings and backups; it is not a self-contained data directory. Set `LIBRARY_MANAGER_DATA_DIR` only when you need a separate development or test location.

## ⚙️ Version 1.0.0 changes

- **Libraries** and **History** now open from **Settings**.
- **Current Library** lists all indexed songs. Destructive delete/duplicate actions show a warning and review step; delete verifies a safety copy before removing a local original.
- **Clear history** also deletes Field journal entries. Once cleared, metadata edits can no longer be undone from those entries.
- Playlist order and playlist-artwork changes depend on safe operations exposed by the installed classic iTunes COM interface. Unsupported operations report the limitation instead of modifying song artwork or deleting tracks.

## 🎧 Optional Last.fm

Connect your own API key and username inside the Last.fm page. Internet access is required; the app does not send your library to Last.fm. See the [Last.fm guide](docs/LASTFM.md).
