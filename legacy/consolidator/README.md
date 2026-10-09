# 💿 iTunes Library Consolidator 2.2

Find duplicate tracks in an iTunes XML export, choose the copy to keep and merge ratings, play counts and dates while keeping playlist references.

This is the original Consolidator, available from the new app’s Settings. Some advanced controls are available only here.

## 🛡️ Before using it

Back up the library and review the preview before applying changes. XML output is the main result. Original live COM sync can remove duplicate entries from running classic iTunes; this removal has not been verified against real iTunes. Rebuild and live deletion can be irreversible. The new app’s passed metadata-edit test does not prove these original actions work.

Apple Music does not offer the same classic iTunes COM connection. The app does not decode Apple’s private database or bypass copy protection. Spotify/provider support is limited; the supplied Apple Music API provider is a stub.

## 🚀 Run from source

Requires Python 3.10+. From this folder:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m src.main
```

To build on Windows, run `dist_config\build_windows.bat`. It installs dependencies, runs tests and creates `dist\iTunesLibraryConsolidator\`, then copies the executable and needed files into the project folder. `dist_config\build.bat` offers a build menu and progress window. An executable must keep its bundled dependencies beside it.

See the [original installer guide](dist_config/installer_README.md) or [unified build steps](../../BUILD.md).

## 🎯 Review duplicates

1. Export a library XML from iTunes or Apple Music where that option is available.
2. Open it in Consolidator. Review the change summary if it has been opened before.
3. Review each duplicate group and the chosen copy. Possible matches start unchecked. Select them only after checking.
4. Choose a different copy, mark a group as not duplicated, or manually merge tracks when needed. “Select all (incl. review)” also selects uncertain matches, so review carefully.
5. Preview the plan and write a separate XML. Keep the original export and review live-sync or rebuild choices separately.

## ✨ Advanced tools

Use health reports, local artwork inspection, missing-file relinking, search, audio preview, exclusions, history and named restore points. Backup retention and scheduled checks use the original settings. Review the backup policy before relying on old restore points.

Fuzzy matching has a time budget and may miss possible matches in very large libraries. Exact matches are not limited by that budget. Similarity thresholds range from 0.50 to 0.99; the high-confidence threshold stays above the possible-match threshold. Large scans may use multiple processes and fall back to one process if needed.

## 🧪 Test limits

Original tests use generated libraries, including a 120,000-track fixture, Unicode names, nested playlist folders and malformed XML. Those results do not prove safety on your own collection. From this folder, run `python -m pytest tests/`.

## 📚 Full history and detailed workflows

[Original guide and release history](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/v1.0/legacy/consolidator/README.md) · [Current feature coverage](../../docs/FEATURE_PARITY.md) · [Known limits](../../docs/LIMITATIONS.md).
