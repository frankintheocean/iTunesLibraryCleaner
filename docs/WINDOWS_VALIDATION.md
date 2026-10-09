# Windows installer and live iTunes validation

## Installer build

The **Windows installer** GitHub Actions workflow builds on a Windows Server 2022 x64 runner after a main-branch push or a manual dispatch. It installs the Windows dependency lock, runs the original and unified tests, builds the frontend, freezes Python, exercises the actual frozen backend, and packages Electron as an unsigned assisted NSIS installer.

The next step silently installs the application, runs the real packaged Electron workflow against synthetic fixtures, repairs a deliberately deleted backend executable, uninstalls, and reinstalls. It verifies that the generated application-state SQLite database remains byte-identical across uninstall/reinstall. Screenshots and validation JSON are uploaded separately from the installer and SHA-256 checksums. A successful Actions artifact establishes those checks on the hosted runner; it does not establish Windows 10/11, high-DPI, manual shortcut/registry, signing, or live iTunes acceptance.

Download artifacts from the successful run on the repository's Actions page. `windows-x64-installer-<commit>` contains the installer. `windows-validation-<commit>` contains evidence. Installer packaging explicitly disables Electron Builder publication; only validated Actions artifacts are uploaded. No successful acceptance run is claimed until that run completes successfully.

Local alternative, with Python 3.12 x64 and Node 24 installed:

```powershell
powershell -File scripts/build-windows.ps1
powershell -File scripts/test-windows-installer.ps1
```

The installer test installs into a new temporary directory and intentionally leaves its synthetic acceptance state and diagnostics for review. It creates normal installer shortcuts and uninstall registration, so use a disposable Windows test account/VM without an existing installation. Release signing is not configured.

## Live COM on your Windows machine

1. Install **classic iTunes for Windows** and Python 3.12 x64. Apple Music for Windows does not expose this COM interface.
2. Close iTunes. Hold **Shift** while starting it and choose **Create Library**. Create a new empty disposable library in a separate test directory. Keep this library open and dismiss setup/modal dialogs.
3. In a checkout of this repository, run:

   ```powershell
   powershell -File scripts/validate-live-com.ps1
   ```

   The script installs the pinned Windows dependencies and refuses to proceed if the active library contains any tracks. It creates and imports two one-second silent WAVs, verifies their imported media hashes (including when iTunes copies them into its Media folder), then uses the application's real isolated COM worker, live scan, preview/queue/commit, journal and undo paths. All 14 supported fields are tested: genre, title, artist, album, album artist, year, track/disc numbers and totals, composer, comment, compilation and rating. Readback uses a separate live COM connection. An external edit to the synthetic track's genre tests that undo preserves concurrent changes while restoring the other fields.

4. Inspect the console result and `build/live-com-validation/<run-id>/report.json`. The same directory contains the SQLite journal and synthetic media. Tracks and files are retained for review; the script never deletes tracks. A failed run also saves its report and journal. Resolve any partial outcome before retrying. Subsequent runs require another empty test library.
5. Share `report.json` and any error output here. The report contains only generated fixture identities/paths, the iTunes version and test outcomes. Close iTunes and reopen your normal library with Shift after testing.

Live passing does not establish modal/restart recovery, locked/missing/protected media, high-bit IDs unless actually observed, album-grouping behavior, or the remaining Windows acceptance checklist in TESTING.md. These require separate controlled tests. Never run acceptance against your personal collection.

The unified live scanner uses the documented `IITPlaylist.Source.Playlists` member. The supplied legacy modules retain their original implementation. API reference: [iTunes SDK playlist interface mirror](https://github.com/joshkunz/iTunesControl/blob/22016cb72084c24101d684ef7894a52c78ccb6a9/iTunesCOM/interfaceIITPlaylist.html).

## Desktop iTunes connection compatibility

On Apple-distributed iTunes 12.13.11.1, a real Windows diagnostic confirmed `Dispatch('iTunes.Application')` succeeds with an empty library while `GetActiveObject` returns `MK_E_UNAVAILABLE` (-2147221021). The shared connector now uses Dispatch for that specific failure. This can open classic iTunes during a connection check; other errors propagate unchanged. The validation script still checks that the active library is empty before importing or editing any synthetic tracks. Full live metadata acceptance remains pending.
