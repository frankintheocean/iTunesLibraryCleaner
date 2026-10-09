# 🎵 Unified iTunes Library Manager 1.0

A Windows music-library workspace combining LibraryCleaner and iTunes Library Consolidator with an Apple-inspired interface.

## ✨ Key features

- Edit live iTunes genres, titles, artists, albums and other metadata through classic iTunes COM.
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

Every unified mutation requires a preview and explicit confirmation. COM has no multi-field transaction; partial results are journaled, and undo applies only when values still match the previous write. Backups are retained. Moving files can break live references. Original tools retain their own potentially irreversible deletion and rebuild operations: use their confirmations and backups.

The installer is unsigned. Source-level live COM editing and conditional undo passed on iTunes 12.13.11.1; packaged live COM and additional Windows 10/11 manual acceptance remain outstanding. Read [known limitations](docs/LIMITATIONS.md) and [validation evidence](docs/VALIDATION.md). DRM and proprietary Apple databases are not modified. The application does not upload libraries or publish to GitHub.

## 📚 Guides

[Install](INSTALL.md) · [Build](BUILD.md) · [Tests](TESTING.md) · [Workspace](docs/WORKSPACE_GUIDE.md) · [Feature parity](docs/FEATURE_PARITY.md) · [Architecture](ARCHITECTURE.md) · [Migration](MIGRATION.md) · [Licenses](THIRD_PARTY_LICENSES.md) · [File and folder labels](docs/REPOSITORY_LABELS.md)
