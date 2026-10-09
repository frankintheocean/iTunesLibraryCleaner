# 🎵 iTunes Manager 3.1.0

Read your Last.fm listening history and keep large live iTunes scans moving.

## 🐛 Fixes

- Let live scans continue beyond 15 minutes while songs and playlists are still being read.
- Stop scans that stall, and explain that a read-only scan did not change live metadata.
- Keep cancellation responsive during slow reads. Metadata writes retain their separate timeout safeguards.
- Show the GitHub button only in Settings.

## ✨ New tools

- Connect a Last.fm API key and username. See a large profile picture and total plays.
- Browse recent songs and top songs, artists and albums over six time periods.
- Show available artwork, browse more results and refresh listening data.
- Hide discovered library locations without deleting files or unloading libraries. Restore suggestions whenever you want.

## 📥 Choose a download

- **Installer EXE:** install the app and shortcuts.
- **Windows app ZIP:** extract the whole folder, then open `iTunes Manager.exe`. No Python or Node needed. Settings still use AppData.
- **Source ZIP:** build or review the code and preserved original tools.
- **Checksums and test report:** verify downloads and see the Windows results.

Close the old app before upgrading. Existing libraries, settings and backups keep the same data folder. Requires Windows 10/11 x64; live editing needs classic iTunes. The installer is unsigned.

## 🛡️ Checks and limits

Release downloads must pass the Windows installer, repair, uninstall and package checks for their exact source commit. See the attached report and [test results](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/docs/VALIDATION.md).

The scan timeout tests simulate slow COM workers, and a separate reader test covers 48,000 generated track IDs. Hosted tests do not run classic iTunes, so a fresh scan of a real 48,000-song library still needs user validation.

Last.fm is read-only. An API key and username read public listening data; they do not sign you in to the website or send scrobbles. The key stays in the local, unencrypted app database until you disconnect. Photos appear only when Last.fm provides them. Last.fm tests use provider-shaped fixtures, not a real account. [Last.fm guide](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/docs/LASTFM.md) · [Install guide](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/INSTALL.md) · [All changes](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/CHANGELOG.md)
