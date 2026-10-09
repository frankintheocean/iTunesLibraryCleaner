# 🎵 Version 1.0 — Windows preview

Windows x64 installer built from commit `f33f15a4aefbd9485adb3796dffbfda1e8fb5490`. Application metadata uses `1.0.0`; the release and download names use **1.0**.

Download `Unified-iTunes-Library-Manager-1.0-win-x64.exe`. The adjacent `.sha256` file provides its checksum; `installer-validation.json` records acceptance results.

This version includes the distinct flat record-and-note icon inspired by the supplied ScoutTool style, and the classic iTunes COM activation fallback. The user-run source validation passed on Apple-distributed iTunes 12.13.11.1: all 14 live metadata fields, independent readback and conditional undo.

The Windows Server 2022 runner passed 189 Python tests (one Linux-only test skipped), both IPC tests, frontend compilation, the frozen backend smoke test and the actual packaged Electron workflow. Silent install, repair of a deleted backend, uninstall/reinstall and byte-identical application-state preservation passed. [Validation run](https://github.com/frankintheocean/iTunesLibraryCleaner/actions/runs/37873855493).

The installer is unsigned. Packaged live COM, modal/restart recovery, Windows 10/11 clean-machine acceptance, high-DPI/multi-monitor behavior and manual shortcut checks remain outstanding. This is a testing preview.

[Live COM validation instructions](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/docs/WINDOWS_VALIDATION.md) · [Known limitations](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/docs/LIMITATIONS.md)
