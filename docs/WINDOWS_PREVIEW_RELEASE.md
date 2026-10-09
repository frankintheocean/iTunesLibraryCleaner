# 🎵 Version 1.0 — Windows preview

A Windows music-library app with live iTunes editing, previewed changes, backups and a new flat record-and-note icon.

## 📥 Download

Choose `Unified-iTunes-Library-Manager-1.0-win-x64.exe`. The `.sha256` file checks the download; `installer-validation.json` records the installer test results. The app uses version `1.0.0` internally and **1.0** in download names.

## ✅ What passed

- Real source-level iTunes testing on version 12.13.11.1: all 14 supported metadata fields, a separate readback and undo that preserves later changes.
- Windows Server 2022: 189 Python tests passed, one Linux-only test skipped, both IPC tests passed, and the interface and bundled backend checks passed.
- Installer checks: install, packaged app use, repair, uninstall/reinstall and unchanged saved app data.

[Build and test run](https://github.com/frankintheocean/iTunesLibraryCleaner/actions/runs/37873855493). The installer was built from `f33f15a4aefbd9485adb3796dffbfda1e8fb5490`.

## 🚧 Before using it

This installer is unsigned and is a testing preview. Live iTunes editing through the installed app still needs testing. Windows 10/11 clean-machine checks, open-dialog/restart recovery, multiple monitors, display scaling and manual shortcut checks also remain.

Use a disposable empty library for live testing. Do not test on your personal music collection.

[Live test steps](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/docs/WINDOWS_VALIDATION.md) · [Known limits](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/docs/LIMITATIONS.md)
