# Testing

Run `.venv/bin/python -m pytest tests legacy/consolidator/tests -q`, `npm test`, and `npm run build`. New tests use temporary synthetic XML, FLAC metadata headers and byte files; real COM objects are replaced with deterministic contract fakes for signed IDs, multi-field writes, concurrent changes, rejected-call reconnect and partial failures. Fake COM passing is not real iTunes validation.

Filesystem tests cover staging hashes, quarantine restore, no-overwrite behavior, changed sources, collisions, Unicode/reserved names, traversal and symlink rejection. Integration tests cover streaming import, duplicate merge metadata/playcounts, playlist ordering, original-file preservation, authenticated API, explicit confirmation, custom rules, history/settings and interrupted checkpoints. Original suites retain their exact algorithms and fixtures including large-library tests.

Desktop integration: `npm run test:desktop` starts Electron against disposable generated fixtures. Linux CI needs an available X display. In this restricted container only, Chromium's SUID sandbox cannot be configured, so the tested command used `DISPLAY=:99 LIBRARY_MANAGER_TEST_NO_SANDBOX=1 npm run test:desktop`. That explicit flag belongs to the test harness, never the production app configuration. Real Windows sandbox acceptance remains required. Screenshots are under `docs/`.

## Required Windows acceptance before release

Use a disposable classic iTunes library with synthetic media, never the user's collection. Validate a real live scan, genre normalization, title/artist/album/album-artist edits, track/disc numbers, ratings, album merge and conditional undo. Exercise files that are read-only/locked, missing tracks, modal iTunes dialogs, stopped/restarted iTunes and high-bit persistent IDs. Confirm partial failures match journals and live readback.

Build and install on clean Windows 10 and 11 x64 without Python/Node. Verify backend startup, all native dialogs, icons in taskbar/Start Menu/shortcuts/Apps & Features, resize/drag/maximize/restore at multiple DPIs and monitors, keyboard focus, dark/high contrast themes and virtualized paging. Open both bundled legacy interfaces.

Remove a packaged file and shortcut, rerun the installer/maintenance launcher and verify repair. Uninstall/reinstall and verify settings, backups, exports and music remain. Test child-process shutdown with running/interrupted operations. Check source/destination overlap, insufficient disk space, locked/Unicode/long paths, case collisions, network shares/disconnected disks and filesystems without hard links. Such paths are not claimed validated on Linux.

See docs/VALIDATION.md for actual outcomes, not an implied checklist pass.

Executable acceptance entry points are documented in [Windows validation](docs/WINDOWS_VALIDATION.md): `scripts/test-windows-installer.ps1` and `scripts/validate-live-com.ps1`. Hosted builds do not run classic iTunes.
