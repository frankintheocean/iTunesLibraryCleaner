# 🎵 iTunes Manager 3.0.0

Faster library loading and search, safer live edits, and clearer progress.

## 📥 Choose a download

- **Installer EXE:** install the app and Windows shortcuts.
- **Windows app ZIP:** extract every file, then open `iTunes Manager.exe`. No Python or Node needed. Settings and backups still use AppData.
- **Source ZIP:** build or review the code. Includes the built interface, guides and preserved tools.
- **Checksums and test report:** verify the downloads and see the Windows acceptance results.

Requires Windows 10/11 x64. Live editing needs classic iTunes; Apple Music for Windows does not expose this connection.

## 🐛 Fixes

- Keep loaded and selected libraries when switching tabs or collections.
- Count down ETA and wait until saving is finished before showing 100%.
- Avoid overwriting a snapshot Windows may have locked.
- Find live songs by exact track ID even when iTunes’ direct lookup misses them.
- Retry temporary connection failures and show clear service errors.
- Fill missing XML sizes from local files and fix dark-theme overview labels.

## ⚡ Faster work

- Parse large XML exports once and reuse loaded libraries.
- Use a text search index and stop reloading unrelated pages while typing.
- Update only edited search rows after metadata changes.
- Reuse track IDs for live playlist links and check the open library’s identity.

## ✨ New tools

- Remove library profiles without deleting music or saved records.
- Clear visible history while keeping undo and file restore records.
- Show notifications that disappear, whole genre percentages and song counts.
- Show supported playlist pictures or choose your own for the app.
- Set your default library XML path, including on another drive.
- Use a new geometric icon inspired by ScoutTool’s colors and simple style.

## 🛡️ Checks and limits

The download workflow requires a successful Windows installer test run for the exact source commit. It verifies archive records and checksums before publishing. See the attached report and [test results](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/docs/VALIDATION.md).

The installer is unsigned. Hosted Windows checks do not run classic iTunes. Source-level real COM validation passed earlier on iTunes 12.13.11.1; the new lookup paths and installed-app live editing still need a real iTunes check. Classic COM does not expose custom playlist pictures; choosing a picture changes this app only. ETA and speed depend on the work and hardware.

Close the old app before upgrading. Existing libraries, settings, backups and history keep the same data folder. Review previews and partial results before retrying. [Install guide](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/INSTALL.md) · [All changes](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/CHANGELOG.md) · [Known limits](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/docs/LIMITATIONS.md)
