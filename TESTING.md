# 🧪 Run checks

## ⚡ Development checks

From the repository folder, run:

```sh
.venv/bin/python -m pytest tests legacy/consolidator/tests -q
npm test
npm run build
```

Tests use temporary libraries and media. COM test doubles check IDs, multi-field edits, reconnects, concurrent changes and partial failures. They do not prove that real iTunes works.

File tests check verified copies, restore, collisions, changed sources, Unicode and reserved names, path traversal and symlinks. API tests check imports, duplicate merges, playlist order, authentication, confirmations, rules, history and interrupted work. The original test suites remain available.

## 🖥️ Desktop checks

`npm run test:desktop` starts Electron with generated test data. Linux needs a display. This restricted cloud used `DISPLAY=:99 LIBRARY_MANAGER_TEST_NO_SANDBOX=1 npm run test:desktop` because it cannot configure Chromium's SUID sandbox helper. That flag is for this test harness only; production sandboxing stays enabled. Screenshots are in `docs/`.

## 🪟 Checks still needed before a production release

Use a disposable classic iTunes library with generated media. Never use your personal collection.

- Test live scans, genre cleanup, album merging, all supported metadata fields and conditional undo.
- Test locked, read-only, missing and protected media, open iTunes dialogs, stopped/restarted iTunes and high-bit persistent IDs. Compare partial results with saved change records and live values.
- Install on clean Windows 10 and 11 x64 without Python or Node. Check startup, file dialogs, both original tools, shortcuts, taskbar icons and the uninstall entry.
- Check resize, dragging, maximize/restore, keyboard focus, dark/high-contrast themes and track paging at different display scales and on multiple monitors.
- Remove a packaged file and shortcut, then test repair. Uninstall/reinstall and check that settings, backups, exports and music remain. Check shutdown during running and interrupted jobs.
- Test overlapping folders, low disk space, locked files, Unicode and long paths, case collisions, network shares, disconnected drives and filesystems without hard links.

[Windows procedures](docs/WINDOWS_VALIDATION.md) explain the installer and live COM scripts. Hosted builds do not run classic iTunes. See [actual results](docs/VALIDATION.md); this list is not a record of passed tests.
