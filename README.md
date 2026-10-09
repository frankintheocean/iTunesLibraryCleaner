# 🎵 Unified iTunes Library Manager 1.0

A Windows music-library workspace combining LibraryCleaner and iTunes Library Consolidator with an Apple-inspired interface.

## ✨ Key features

- Edit live iTunes genres, titles, artists, albums and other metadata through classic iTunes’ Windows connection (COM).
- Clean genres, merge split albums, find duplicates and organize media.
- Preview changes, retain backups and review queued jobs and undo history.
- Launch preserved original tools for advanced workflows.

## 🚀 Quick start

Download the Windows installer from [GitHub Releases](https://github.com/frankintheocean/iTunesLibraryCleaner/releases). Requires Windows 10/11 x64; live editing requires **classic iTunes**, not Apple Music for Windows.

To run from source, install Python 3.12+ and Node 22.12+, then run in the repository folder:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-lock-windows.txt
npm ci
npm run build
npm run desktop
```

Open classic iTunes before connecting. Linux development uses `requirements-lock-linux.txt`; live COM and Windows packaging require Windows. Electron needs a graphical display.

## 🛡️ Before editing

Review a preview and confirm before the new app changes anything. An iTunes edit can partly succeed; the app records each result. Undo changes a field only if it still matches the app’s last write. Backups are retained. Moving files can break live references. Original tools retain their own deletion and rebuilding actions that may be irreversible: use their confirmations and backups.

The installer is unsigned. Source-level live COM editing and undo that keeps later changes passed on iTunes 12.13.11.1; live editing through the installed app and further Windows 10/11 checks still need testing. Read [known limitations](docs/LIMITATIONS.md) and [validation evidence](docs/VALIDATION.md). Copy-protected media (DRM) and Apple’s private database formats are not changed. The application does not upload libraries or publish to GitHub.

## 📚 Guides

[Install](INSTALL.md) · [Build](BUILD.md) · [Tests](TESTING.md) · [Workspace](docs/WORKSPACE_GUIDE.md) · [Feature coverage](docs/FEATURE_PARITY.md) · [Architecture](ARCHITECTURE.md) · [Migration](MIGRATION.md) · [Licenses](THIRD_PARTY_LICENSES.md) · [File and folder labels](docs/REPOSITORY_LABELS.md)
