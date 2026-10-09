# 🪟 Windows checks

## 📦 Build and test the installer

The Windows installer workflow runs on Windows Server 2022 x64. It installs locked dependencies, runs tests, builds the interface and Python bundle, checks backend startup and creates an unsigned installer.

It then installs the app, tests the packaged interface with generated data, repairs a deleted backend, uninstalls and reinstalls. It checks that the saved app database has not changed. Installer/checksum files and test reports/screenshots are uploaded separately.

On the Actions page, download `windows-x64-installer-<commit>` for the installer and `windows-validation-<commit>` for evidence. Packaging does not publish automatically; only successful, validated builds are used for releases.

To run locally with Python 3.12 x64 and Node 24:

```powershell
powershell -File scripts/build-windows.ps1
powershell -File scripts/test-windows-installer.ps1
```

Use a disposable test account or VM without an existing installation. The test creates normal shortcuts and an uninstall entry, and leaves generated data and reports for review. It does not prove Windows 10/11, manual shortcut, signing, display-scaling or live iTunes support.

## 🎵 Test real iTunes editing

1. Install classic iTunes for Windows and Python 3.12 x64. Apple Music does not offer this COM connection.
2. Close iTunes. Hold **Shift** while opening it, choose **Create Library**, and make a new empty library in a separate test folder. Keep it open and dismiss setup dialogs.
3. From the repository folder, run:

   ```powershell
   powershell -File scripts/validate-live-com.ps1
   ```

4. Review the console and `build/live-com-validation/<run-id>/report.json`. The folder also holds the database journal and generated media. A failure still saves a report. Review partial edits before retrying. Each run needs another empty library.
5. Share the report and any errors for review. It contains generated track IDs/paths, the iTunes version and results. Close iTunes and use Shift to reopen your normal library afterward.

The script installs locked dependencies and refuses a library that already has tracks. It imports two one-second silent WAVs and checks their hashes, including copies made by iTunes. It uses the real app scan, preview, queue, edit records and undo worker.

It tests all 14 fields: genre, title, artist, album, album artist, year, track/disc numbers and totals, composer, comments, compilation and rating. A separate connection checks the results. A later genre edit tests whether undo preserves later changes while restoring the other fields. Tracks and files are kept; the script never deletes tracks.

**Never run this against your personal collection.** A pass does not prove dialog/restart recovery, locked/missing/protected media, album grouping or high-bit IDs unless seen in that run. See [remaining checks](../TESTING.md).

## 🔌 Connection behavior

On Apple’s iTunes 12.13.11.1, `GetActiveObject` returned `MK_E_UNAVAILABLE` (-2147221021), but `Dispatch('iTunes.Application')` connected successfully. The shared connector uses Dispatch only for that error; it can open iTunes. Other errors remain visible. The empty-library check still runs before importing or editing test tracks.

After the fix, the user-run source test passed all 14 fields, separate readback and conditional undo. The detailed JSON was not supplied. Installed-app live editing and other manual checks still need testing.

The new scanner uses `IITPlaylist.Source.Playlists`. Original modules keep their own code. [iTunes SDK reference](https://github.com/joshkunz/iTunesControl/blob/22016cb72084c24101d684ef7894a52c78ccb6a9/iTunesCOM/interfaceIITPlaylist.html).
